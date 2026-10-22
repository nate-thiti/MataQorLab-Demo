"""Chat service — composes ingest, analytics, agent, context, and stream modules."""
from __future__ import annotations

from typing import AsyncIterator

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat.agent_bridge import AgentAnalyticsBridge
from app.services.chat.context_builder import ChatContextBuilder
from app.services.chat.ingest import DataIngestService
from app.services.chat.llm_client import LlmClient
from app.services.chat.pandas_analytics import PandasAnalyticsEngine
from app.services.chat.stream_handler import ChatStreamHandler


class ChatService:
    def __init__(self) -> None:
        self.llm = LlmClient()
        self.analytics = PandasAnalyticsEngine()
        self.ingest = DataIngestService(self.llm, self.analytics)
        self.agent = AgentAnalyticsBridge(self.llm)
        self.context = ChatContextBuilder(self.llm, self.ingest, self.analytics, self.agent)
        self.stream = ChatStreamHandler(self.llm, self.context)

    async def prepare_chat_context(self, chat_request, on_status=None):
        return await self.context.prepare(chat_request, on_status=on_status)

    async def stream_chat_completion(self, chat_request: ChatRequest) -> AsyncIterator[str]:
        async for event in self.stream.stream_chat_completion(chat_request):
            yield event

    async def get_chat_completion(self, chat_request: ChatRequest) -> ChatResponse:
        return await self.stream.get_chat_completion(chat_request)


chat_service = ChatService()
