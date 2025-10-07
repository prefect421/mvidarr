#!/usr/bin/env python3
"""
Monitor the new metadata enrichment job
"""

import asyncio
import json
import time

import websockets


async def monitor_job_progress(job_id):
    """Monitor job progress via WebSocket"""
    
    print(f"🔗 Connecting to WebSocket to monitor job: {job_id}")
    try:
        async with websockets.connect("ws://localhost:5000/ws/jobs") as websocket:
            print("✅ WebSocket connected")
            
            # Subscribe to the job immediately
            subscribe_message = {
                "type": "subscribe_job",
                "job_id": job_id
            }
            await websocket.send(json.dumps(subscribe_message))
            print(f"📨 Subscribed to job: {job_id}")
            
            # Monitor progress with shorter timeout for quick response
            received_messages = []
            start_time = time.time()
            
            try:
                while time.time() - start_time < 30:  # 30 second timeout
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                        data = json.loads(message)
                        received_messages.append(data)
                        
                        msg_type = data.get("type", "unknown")
                        timestamp = time.strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
                        
                        if msg_type == "job_update":
                            job_data = data.get("data", {})
                            progress = job_data.get("progress", job_data.get("percent", 0))
                            msg = job_data.get("message", "")
                            status = job_data.get("status", "")
                            
                            print(f"🎯 [{timestamp}] {progress:3}% - {msg} (status: {status})")
                            
                            # Check if job is complete
                            if progress >= 100 or status in ["SUCCESS", "completed"]:
                                print("✅ Job completed successfully!")
                                break
                            elif status in ["FAILURE", "failed"]:
                                print("❌ Job failed!")
                                break
                                
                        elif msg_type == "connected":
                            print(f"🔗 [{timestamp}] Connected: {data.get('message', '')}")
                        elif msg_type == "subscription_response":
                            success = data.get("success", False)
                            msg = data.get("message", "")
                            print(f"📨 [{timestamp}] Subscription {'✅' if success else '❌'}: {msg}")
                        elif msg_type == "job_status":
                            job_data = data.get("data", {})
                            progress = job_data.get("progress", job_data.get("percent", 0))
                            msg = job_data.get("message", "")
                            print(f"📊 [{timestamp}] Current status: {progress}% - {msg}")
                        else:
                            print(f"📨 [{timestamp}] {msg_type}: {json.dumps(data, indent=2)}")
                            
                    except asyncio.TimeoutError:
                        continue  # Continue listening
                        
            except Exception as e:
                print(f"❌ WebSocket error: {e}")
            
            # Summary
            print(f"\n📊 Monitoring Summary:")
            print(f"   Total messages: {len(received_messages)}")
            job_updates = [msg for msg in received_messages if msg.get("type") == "job_update"]
            print(f"   Job updates: {len(job_updates)}")
            
            if job_updates:
                progress_values = [msg.get("data", {}).get("progress", msg.get("data", {}).get("percent", 0)) for msg in job_updates]
                print(f"   Progress sequence: {progress_values}")
                
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")


if __name__ == "__main__":
    job_id = "fabfbfc3-4777-4870-b8ce-d22f0709dd26"  # New job ID
    print(f"🔍 Monitoring metadata enrichment job: {job_id}")
    print("=" * 60)
    
    asyncio.run(monitor_job_progress(job_id))