#!/usr/bin/env python3
"""
Test script for Chatterbox TTS integration
Verifies API connectivity and audio generation
"""

import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()


async def test_chatterbox_health():
    """Test if Chatterbox server is running"""
    url = os.getenv("CHATTERBOX_API_URL", "http://localhost:4123")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Try health endpoint
            async with session.get(f"{url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    print("✅ Chatterbox server is running")
                    return True
                else:
                    print(f"⚠️  Chatterbox health check returned status {response.status}")
                    return False
    except aiohttp.ClientConnectorError:
        print(f"❌ Cannot connect to Chatterbox at {url}")
        print("   Make sure the server is running on the correct port")
        return False
    except asyncio.TimeoutError:
        print(f"❌ Connection timeout to {url}")
        return False
    except Exception as e:
        print(f"❌ Error checking Chatterbox: {e}")
        return False


async def test_chatterbox_synthesis():
    """Test audio synthesis"""
    url = os.getenv("CHATTERBOX_API_URL", "http://localhost:4123")
    
    payload = {
        "input": "Hello! This is a test of the Chatterbox text to speech system.",
        "exaggeration": float(os.getenv("CHATTERBOX_EXAGGERATION", "0.5")),
        "cfg_weight": float(os.getenv("CHATTERBOX_CFG_WEIGHT", "0.5")),
        "temperature": float(os.getenv("CHATTERBOX_TEMPERATURE", "0.8")),
    }
    
    voice = os.getenv("CHATTERBOX_VOICE")
    if voice:
        payload["voice"] = voice
        print(f"Using voice: {voice}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{url}/v1/audio/speech",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    print(f"✅ Audio synthesis successful")
                    print(f"   Generated {len(audio_data):,} bytes of audio")
                    print(f"   Approximately {len(audio_data) / (24000 * 2):.2f} seconds")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Synthesis failed with status {response.status}")
                    print(f"   Error: {error_text}")
                    return False
    except asyncio.TimeoutError:
        print("❌ Synthesis request timed out (>30s)")
        return False
    except Exception as e:
        print(f"❌ Error during synthesis: {e}")
        return False


async def test_configuration():
    """Test environment configuration"""
    print("\n📋 Configuration Check:")
    print("-" * 50)
    
    required_vars = {
        "CHATTERBOX_API_URL": os.getenv("CHATTERBOX_API_URL", "http://localhost:4123"),
        "OPENAI_API_KEY": "***" if os.getenv("OPENAI_API_KEY") else "Not set",
        "DEEPGRAM_API_KEY": "***" if os.getenv("DEEPGRAM_API_KEY") else "Not set",
        "LIVEKIT_URL": os.getenv("LIVEKIT_URL", "Not set"),
        "LIVEKIT_API_KEY": "***" if os.getenv("LIVEKIT_API_KEY") else "Not set",
    }
    
    optional_vars = {
        "CHATTERBOX_VOICE": os.getenv("CHATTERBOX_VOICE", "default"),
        "LLM_CHOICE": os.getenv("LLM_CHOICE", "gpt-4o-mini"),
        "CHATTERBOX_EXAGGERATION": os.getenv("CHATTERBOX_EXAGGERATION", "0.5"),
        "CHATTERBOX_CFG_WEIGHT": os.getenv("CHATTERBOX_CFG_WEIGHT", "0.5"),
        "CHATTERBOX_TEMPERATURE": os.getenv("CHATTERBOX_TEMPERATURE", "0.8"),
    }
    
    print("\nRequired Configuration:")
    for key, value in required_vars.items():
        status = "✅" if value != "Not set" else "❌"
        print(f"  {status} {key}: {value}")
    
    print("\nOptional Configuration:")
    for key, value in optional_vars.items():
        print(f"  ℹ️  {key}: {value}")
    
    missing = [k for k, v in required_vars.items() if v == "Not set"]
    if missing:
        print(f"\n⚠️  Missing required variables: {', '.join(missing)}")
        return False
    else:
        print("\n✅ All required variables configured")
        return True


async def main():
    """Run all tests"""
    print("=" * 50)
    print("Chatterbox TTS Integration Test")
    print("=" * 50)
    
    # Test configuration
    config_ok = await test_configuration()
    
    print("\n" + "=" * 50)
    print("Testing Chatterbox Connection")
    print("=" * 50)
    
    # Test health
    health_ok = await test_chatterbox_health()
    
    if not health_ok:
        print("\n⚠️  Skipping synthesis test - server not reachable")
        return
    
    # Test synthesis
    print("\n" + "=" * 50)
    print("Testing Audio Synthesis")
    print("=" * 50)
    
    synthesis_ok = await test_chatterbox_synthesis()
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    print(f"Configuration: {'✅ Pass' if config_ok else '❌ Fail'}")
    print(f"Server Health: {'✅ Pass' if health_ok else '❌ Fail'}")
    print(f"Audio Synthesis: {'✅ Pass' if synthesis_ok else '❌ Fail'}")
    
    if config_ok and health_ok and synthesis_ok:
        print("\n🎉 All tests passed! Ready to run the voice agent.")
        print("\nStart the agent with: python agent.py dev")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")


if __name__ == "__main__":
    asyncio.run(main())