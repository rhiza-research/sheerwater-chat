"""FastAPI application for sheerwater-chat."""

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from .auth import create_oauth, get_user_from_session, get_user_id, get_user_name
from .chat import DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT, ChatService
from .config import Config
from .database import Database
from .mcp_client import McpClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
config: Config = None
db: Database = None
mcp_client: McpClient = None
chat_service: ChatService = None
oauth = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global config, db, mcp_client, chat_service, oauth

    config = Config.from_env()
    db = Database(config.database_url)
    mcp_client = McpClient(config.mcp_server_url)
    chat_service = ChatService(config.anthropic_api_key, mcp_client)
    oauth = create_oauth(config)

    # Connect to database
    await db.connect()
    logger.info("Connected to database")

    # Connect to MCP server using proper async context management
    async with mcp_client.connection():
        logger.info("Connected to MCP server")
        yield

    # Cleanup database
    await db.disconnect()


app = FastAPI(title="Sheerwater Chat", lifespan=lifespan)

# Templates and static files
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def require_auth(request: Request):
    """Dependency that requires authentication."""
    user = get_user_from_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# --- Auth Routes ---


@app.get("/login")
async def login(request: Request):
    """Redirect to Keycloak login."""
    redirect_uri = f"{config.base_url}/callback"
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


@app.get("/callback")
async def callback(request: Request):
    """Handle Keycloak callback."""
    token = await oauth.keycloak.authorize_access_token(request)
    user_info = token.get("userinfo")
    if user_info:
        request.session["user"] = dict(user_info)
    return RedirectResponse(url="/")


@app.get("/logout")
async def logout(request: Request):
    """Log out and clear session."""
    request.session.clear()
    return RedirectResponse(url="/")


# --- Page Routes ---


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main chat page."""
    user = get_user_from_session(request)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request})

    user_id = get_user_id(request)
    conversations = await db.list_conversations(user_id)

    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "user_name": get_user_name(request),
            "conversations": conversations,
            "current_conversation": None,
            "messages": [],
        },
    )


@app.get("/c/{conversation_id}", response_class=HTMLResponse)
async def conversation_page(request: Request, conversation_id: str, user: dict = Depends(require_auth)):
    """View a specific conversation."""
    user_id = get_user_id(request)
    conversation = await db.get_conversation(conversation_id, user_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversations = await db.list_conversations(user_id)
    messages = await db.get_messages(conversation_id)

    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "user_name": get_user_name(request),
            "conversations": conversations,
            "current_conversation": conversation,
            "messages": messages,
        },
    )


# --- API Routes ---


class SendMessageRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class SendMessageResponse(BaseModel):
    conversation_id: str
    response: str
    tool_calls: list[dict]


@app.post("/api/chat", response_model=SendMessageResponse)
async def send_chat_message(request: Request, body: SendMessageRequest, user: dict = Depends(require_auth)):
    """Send a message and get a response."""
    user_id = get_user_id(request)

    # Get or create conversation
    if body.conversation_id:
        conversation = await db.get_conversation(body.conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conversation_id = body.conversation_id
    else:
        conversation_id = str(uuid.uuid4())
        await db.create_conversation(conversation_id, user_id)

    # Add user message to database
    await db.add_message(conversation_id, "user", body.message)

    # Get conversation history
    db_messages = await db.get_messages(conversation_id)
    claude_messages = chat_service.format_messages_for_claude(db_messages)

    # Get runtime settings
    model = await db.get_setting("model", DEFAULT_MODEL)
    system_prompt = await db.get_setting("system_prompt", DEFAULT_SYSTEM_PROMPT)

    # Send to Claude with MCP tools
    result = await chat_service.send_message(claude_messages, model=model, system_prompt=system_prompt)

    # Save assistant response
    await db.add_message(
        conversation_id,
        "assistant",
        result["content"],
        tool_calls=result["tool_calls"] if result["tool_calls"] else None,
    )

    # Update conversation title if it's new
    conversation = await db.get_conversation(conversation_id, user_id)
    if not conversation.get("title"):
        # Use first ~50 chars of user message as title
        title = body.message[:50] + ("..." if len(body.message) > 50 else "")
        await db.update_conversation_title(conversation_id, user_id, title)

    return SendMessageResponse(
        conversation_id=conversation_id,
        response=result["content"],
        tool_calls=result["tool_calls"],
    )


@app.get("/api/conversations")
async def list_conversations(request: Request, user: dict = Depends(require_auth)):
    """List user's conversations."""
    user_id = get_user_id(request)
    return await db.list_conversations(user_id)


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(request: Request, conversation_id: str, user: dict = Depends(require_auth)):
    """Delete a conversation."""
    user_id = get_user_id(request)
    await db.delete_conversation(conversation_id, user_id)
    return {"status": "deleted"}


@app.get("/api/tools")
async def list_tools(user: dict = Depends(require_auth)):
    """List available MCP tools."""
    tools = await mcp_client.list_tools()
    return [{"name": t.name, "description": t.description} for t in tools]


@app.get("/api/settings")
async def get_settings(user: dict = Depends(require_auth)):
    """Get current settings with defaults."""
    settings = await db.get_all_settings()
    return {
        "model": settings.get("model", DEFAULT_MODEL),
        "system_prompt": settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
    }


class UpdateSettingsRequest(BaseModel):
    model: str | None = None
    system_prompt: str | None = None


@app.put("/api/settings")
async def update_settings(body: UpdateSettingsRequest, user: dict = Depends(require_auth)):
    """Update settings."""
    if body.model is not None:
        await db.set_setting("model", body.model)
    if body.system_prompt is not None:
        await db.set_setting("system_prompt", body.system_prompt)
    return await get_settings(user)


def run():
    """Run the application."""
    import uvicorn

    config = Config.from_env()

    # Add session middleware
    app.add_middleware(SessionMiddleware, secret_key=config.secret_key)

    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    run()
