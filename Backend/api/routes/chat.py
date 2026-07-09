"""
POST /api/chat — Agent REST fallback (non-streaming)
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from api.dependencies import fridge_graph, get_current_inventory

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str = Field(default="default")


class ChatResponse(BaseModel):
    reply: str
    thread_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not fridge_graph:
        return ChatResponse(
            reply="Agent not initialized, please try again later",
            thread_id=req.thread_id,
        )

    config = {"configurable": {"thread_id": req.thread_id}}
    inventory = get_current_inventory()

    result = await fridge_graph.ainvoke(
        {
            "messages": [{"role": "user", "content": req.message}],
            "current_inventory": inventory,
        },
        config=config,
    )

    reply = result["messages"][-1].content if result.get("messages") else ""
    return ChatResponse(reply=reply, thread_id=req.thread_id)
