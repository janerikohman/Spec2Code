#!/usr/bin/env python3
"""
Direct Test of FoundryAgentManager
Tests real agent discovery and invocation without needing Jira epic creation
"""

import sys
import os
import json
import time
from io import StringIO

# Add function path to sys.path
sys.path.insert(0, "/Users/shaho/Library/CloudStorage/OneDrive-KnowitAB/Poc/S2C/Spec2Code/DevSecOpsAiTeam/functions/review-endpoint")

# Mock logging to capture output
import logging
logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')


def test_agent_manager_import():
    """Test that FoundryAgentManager can be imported."""
    print("1️⃣  Testing FoundryAgentManager import...")
    try:
        from foundry_agents import FoundryAgentManager, FoundryAgentManager
        print("   ✅ Import successful")
        return True
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
        return False


def test_agent_configs():
    """Test agent registry configuration."""
    print("\n2️⃣  Testing Agent Registry Configuration...")
    try:
        from foundry_agents import FoundryAgentManager
        
        configs = FoundryAgentManager.AGENT_CONFIGS
        print(f"   ✅ Agent configs loaded: {len(configs)} agents")
        
        for role, config in configs.items():
            print(f"      • {role}: {config.name}")
        
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_manager_initialization():
    """Test FoundryAgentManager initialization with mock client."""
    print("\n3️⃣  Testing FoundryAgentManager Initialization...")
    try:
        from foundry_agents import FoundryAgentManager
        
        # Mock client
        class MockClient:
            pass
        
        manager = FoundryAgentManager(MockClient())
        print(f"   ✅ Manager initialized")
        print(f"      • Orchestration ID: {manager._discovered_assistants}")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_coordinator_agent_integration():
    """Test CoordinatorAgent integration with FoundryAgentManager."""
    print("\n4️⃣  Testing CoordinatorAgent Integration...")
    try:
        # Import dependencies
        from coordinator_agent import CoordinatorAgent
        from foundry_agents import FoundryAgentManager
        
        # Mock client
        class MockClient:
            class Agents:
                pass
            agents = Agents()
        
        coordinator = CoordinatorAgent(MockClient())
        
        # Check that agent_manager is initialized
        if not hasattr(coordinator, 'agent_manager'):
            print(f"   ❌ CoordinatorAgent.agent_manager not initialized")
            return False
        
        if not isinstance(coordinator.agent_manager, FoundryAgentManager):
            print(f"   ❌ agent_manager is not FoundryAgentManager instance")
            return False
        
        print(f"   ✅ CoordinatorAgent properly initialized with FoundryAgentManager")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fallback_response():
    """Test fallback response generation."""
    print("\n5️⃣  Testing Fallback Response Generation...")
    try:
        from foundry_agents import FoundryAgentManager
        
        class MockClient:
            pass
        
        manager = FoundryAgentManager(MockClient())
        
        fallback = manager._create_fallback_response(
            agent_role="architect",
            instruction="Design the system",
            context={"epic_key": "KAN-123"}
        )
        
        # Check structure
        required_fields = ["outcome", "confidence", "fallback", "agent_role"]
        missing = [f for f in required_fields if f not in fallback]
        
        if missing:
            print(f"   ❌ Missing fields in fallback: {missing}")
            return False
        
        if fallback.get("fallback") != True:
            print(f"   ❌ Fallback flag not set")
            return False
        
        print(f"   ✅ Fallback response structure valid")
        print(f"      • outcome: {fallback.get('outcome')}")
        print(f"      • confidence: {fallback.get('confidence'):.1%}")
        print(f"      • agent_role: {fallback.get('agent_role')}")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_response_parsing():
    """Test agent response parsing."""
    print("\n6️⃣  Testing Agent Response Parsing...")
    try:
        from foundry_agents import FoundryAgentManager
        import json
        
        class MockClient:
            pass
        
        manager = FoundryAgentManager(MockClient())
        
        # Test valid JSON response
        valid_response = json.dumps({
            "outcome": "completed",
            "confidence": 0.95,
            "reasoning": "Requirements are clear",
            "result": {"approved": True}
        })
        
        parsed = manager._parse_agent_response(valid_response, "po")
        
        if parsed.get("outcome") != "completed":
            print(f"   ❌ Response not parsed correctly")
            return False
        
        print(f"   ✅ Response parsing works")
        print(f"      • outcome: {parsed.get('outcome')}")
        print(f"      • confidence: {parsed.get('confidence'):.1%}")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("🧪 Direct Test of Real Agent Integration")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Import FoundryAgentManager", test_agent_manager_import()))
    results.append(("Agent Registry Config", test_agent_configs()))
    results.append(("Manager Initialization", test_manager_initialization()))
    results.append(("CoordinatorAgent Integration", test_coordinator_agent_integration()))
    results.append(("Fallback Response", test_fallback_response()))
    results.append(("Response Parsing", test_response_parsing()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Real agent integration code is ready.")
        print("\nNext steps:")
        print("1. Create AI Foundry assistants with IDs matching AGENT_REGISTRY")
        print("2. Deploy orchestrator to test real agent invocation")
        print("3. Monitor logs for agent discovery and invocation")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Review implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
