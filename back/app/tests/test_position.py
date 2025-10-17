import pytest
from app.api.schemas import Citation, Target
from app.core.position import resolve_position

def test_resolve_by_url():
    citations = [Citation(url="https://a.com", title="A"), Citation(url="https://b.com", title="B")]
    target = Target(url="https://b.com")
    assert resolve_position(citations, target) == 2

def test_resolve_by_domain():
    citations = [Citation(url="https://shop.example.com", title="Shop")]
    target = Target(domain="example.com")
    assert resolve_position(citations, target) == 1

def test_resolve_by_brand():
    citations = [Citation(url="https://x.com", title="Best Brand")]
    target = Target(brand="Brand")
    assert resolve_position(citations, target) == 1

def test_resolve_none():
    citations = [Citation(url="https://a.com", title="A")]
    target = Target(domain="nope.com")
    assert resolve_position(citations, target) is None
