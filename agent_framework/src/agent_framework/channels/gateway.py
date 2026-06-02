from .adapters import WebAdapter, WhatsAppAdapter, VoiceAdapter
from .base import ChannelResponse

class ChannelGateway:
    def __init__(self):
        self.adapters = {a.name:a for a in [WebAdapter(), WhatsAppAdapter(), VoiceAdapter()]}
    def get(self, channel):
        return self.adapters.get(channel, self.adapters['web'])
    async def normalize(self, channel, payload):
        return await self.get(channel).normalize(payload)
    async def render(self, response: ChannelResponse):
        return await self.get(response.channel).render(response)
