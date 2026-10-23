"""RFC-aware robots matching, including wildcard rules and longest-match Allow."""
from protego import Protego

class RobotFileParser:
    def __init__(self, url=None):
        self.policy = Protego.parse('')
    def parse(self, lines):
        self.policy = Protego.parse('\n'.join(lines))
    def can_fetch(self, user_agent, url):
        return self.policy.can_fetch(url, user_agent)
    def crawl_delay(self, user_agent):
        return self.policy.crawl_delay(user_agent)
    def request_rate(self, user_agent):
        return self.policy.request_rate(user_agent)
