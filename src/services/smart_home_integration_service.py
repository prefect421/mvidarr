"""
Smart Home Integration Service - Phase 4 Week 31
Simple casting and media server compatibility for consumer self-hosting
"""

import asyncio
import json
import socket
import struct
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import aiohttp

from src.utils.logger import get_logger
from src.services.redis_service import get_redis_client
from src.database.async_connection import get_async_session
from src.database.models import Video, Artist
from sqlalchemy import select

logger = get_logger("mvidarr.smart_home")

class CastDeviceType(Enum):
    """Types of casting devices"""
    CHROMECAST = "chromecast"
    APPLE_TV = "apple_tv"
    DLNA_DMR = "dlna_dmr"          # DLNA Digital Media Renderer
    ROKU = "roku"
    FIRE_TV = "fire_tv"
    SMART_TV = "smart_tv"
    WEB_BROWSER = "web_browser"    # Browser-based casting

class CastState(Enum):
    """Cast session states"""
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    PLAYING = "playing"
    PAUSED = "paused"
    BUFFERING = "buffering"
    DISCONNECTED = "disconnected"
    ERROR = "error"

class MediaType(Enum):
    """Types of media being cast"""
    VIDEO = "video"
    AUDIO = "audio"
    PLAYLIST = "playlist"
    LIVE_STREAM = "live_stream"

@dataclass
class CastDevice:
    """Discovered cast device"""
    device_id: str
    name: str
    device_type: CastDeviceType
    ip_address: str
    port: int
    capabilities: List[str]
    manufacturer: str
    model: str
    is_available: bool
    last_seen: datetime
    supported_formats: List[str]
    max_resolution: str

@dataclass
class CastSession:
    """Active cast session"""
    session_id: str
    device_id: str
    device_name: str
    video_id: Optional[int]
    playlist_id: Optional[str]
    state: CastState
    position_seconds: int
    duration_seconds: int
    volume_level: float  # 0.0 - 1.0
    is_muted: bool
    started_at: datetime
    last_update: datetime
    media_url: str
    media_title: str
    media_artist: str

@dataclass
class StreamingInfo:
    """Video streaming information"""
    video_id: int
    stream_url: str
    thumbnail_url: str
    title: str
    artist: str
    duration: int
    quality: str
    format: str
    bitrate: int

class SmartHomeIntegrationService:
    """Smart home and casting integration service"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        
        # Service configuration
        self.server_host = self.config.get('server_host', '0.0.0.0')
        self.server_port = self.config.get('server_port', 5000)
        self.enable_mdns = True
        self.enable_dlna = True
        self.enable_upnp = True
        
        # Device discovery
        self.discovery_interval = 60  # seconds
        self.device_timeout = 300     # 5 minutes
        self.max_devices = 20
        
        # Casting settings
        self.default_quality = "720p"
        self.supported_video_formats = ["mp4", "mkv", "avi", "mov"]
        self.supported_audio_formats = ["mp3", "aac", "flac"]
        
        # Active sessions
        self.active_sessions: Dict[str, CastSession] = {}
        self.discovered_devices: Dict[str, CastDevice] = {}
        
        # DLNA/UPnP settings
        self.dlna_server_name = "MVidarr Media Server"
        self.upnp_uuid = "mvidarr-media-server-001"
        
    async def initialize(self):
        """Initialize smart home integration service"""
        try:
            self.redis_client = await get_redis_client()
            
            # Start device discovery
            asyncio.create_task(self._start_device_discovery())
            
            # Start DLNA/UPnP server if enabled
            if self.enable_dlna:
                asyncio.create_task(self._start_dlna_server())
            
            logger.info("Smart home integration service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize smart home integration service: {e}")
            raise
    
    async def discover_devices(self, timeout: int = 10) -> List[CastDevice]:
        """Discover available casting devices"""
        try:
            logger.info("Starting device discovery...")
            
            # Discover different types of devices concurrently
            discovery_tasks = [
                self._discover_chromecast_devices(),
                self._discover_dlna_devices(),
                self._discover_apple_tv_devices(),
                self._discover_smart_tv_devices()
            ]
            
            # Wait for all discovery methods to complete
            discovery_results = await asyncio.gather(*discovery_tasks, return_exceptions=True)
            
            # Combine results
            all_devices = []
            for result in discovery_results:
                if isinstance(result, list):
                    all_devices.extend(result)
                elif isinstance(result, Exception):
                    logger.warning(f"Device discovery failed: {result}")
            
            # Update device cache
            for device in all_devices:
                self.discovered_devices[device.device_id] = device
                await self._cache_device(device)
            
            # Remove old devices
            await self._cleanup_old_devices()
            
            logger.info(f"Discovered {len(all_devices)} casting devices")
            return all_devices
            
        except Exception as e:
            logger.error(f"Failed to discover devices: {e}")
            return []
    
    async def get_available_devices(self) -> List[CastDevice]:
        """Get list of available casting devices"""
        try:
            # Get cached devices
            cached_devices = await self._get_cached_devices()
            
            # Filter for available devices
            available_devices = [
                device for device in cached_devices
                if device.is_available and 
                (datetime.now() - device.last_seen).total_seconds() < self.device_timeout
            ]
            
            return available_devices
            
        except Exception as e:
            logger.error(f"Failed to get available devices: {e}")
            return []
    
    async def cast_video(
        self,
        video_id: int,
        device_id: str,
        quality: str = None,
        start_position: int = 0
    ) -> Dict[str, Any]:
        """Cast a video to a device"""
        try:
            # Get device info
            device = self.discovered_devices.get(device_id)
            if not device:
                device = await self._get_cached_device(device_id)
                
            if not device or not device.is_available:
                return {
                    'success': False,
                    'message': 'Device not available'
                }
            
            # Get video streaming info
            streaming_info = await self._get_video_streaming_info(video_id, quality)
            if not streaming_info:
                return {
                    'success': False,
                    'message': 'Video not found or not streamable'
                }
            
            # Create cast session
            session_id = f"cast_{int(datetime.now().timestamp())}_{device_id}"
            cast_session = CastSession(
                session_id=session_id,
                device_id=device_id,
                device_name=device.name,
                video_id=video_id,
                playlist_id=None,
                state=CastState.CONNECTING,
                position_seconds=start_position,
                duration_seconds=streaming_info.duration,
                volume_level=0.5,
                is_muted=False,
                started_at=datetime.now(),
                last_update=datetime.now(),
                media_url=streaming_info.stream_url,
                media_title=streaming_info.title,
                media_artist=streaming_info.artist
            )
            
            # Start casting based on device type
            cast_result = await self._start_cast_session(device, cast_session, streaming_info)
            
            if cast_result['success']:
                # Store active session
                self.active_sessions[session_id] = cast_session
                await self._cache_session(cast_session)
                
                logger.info(f"Started casting video {video_id} to device {device.name}")
                
                return {
                    'success': True,
                    'session_id': session_id,
                    'device_name': device.name,
                    'message': 'Casting started successfully'
                }
            else:
                return cast_result
            
        except Exception as e:
            logger.error(f"Failed to cast video {video_id} to device {device_id}: {e}")
            return {
                'success': False,
                'message': f'Casting failed: {str(e)}'
            }
    
    async def control_cast(
        self,
        session_id: str,
        action: str,
        value: Any = None
    ) -> Dict[str, Any]:
        """Control active cast session"""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                session = await self._get_cached_session(session_id)
                
            if not session:
                return {
                    'success': False,
                    'message': 'Cast session not found'
                }
            
            device = self.discovered_devices.get(session.device_id)
            if not device:
                return {
                    'success': False,
                    'message': 'Device not available'
                }
            
            # Execute control action
            control_result = await self._execute_cast_control(device, session, action, value)
            
            if control_result['success']:
                # Update session state
                session.last_update = datetime.now()
                
                if action == 'play':
                    session.state = CastState.PLAYING
                elif action == 'pause':
                    session.state = CastState.PAUSED
                elif action == 'seek':
                    session.position_seconds = value
                elif action == 'volume':
                    session.volume_level = value
                elif action == 'mute':
                    session.is_muted = value
                
                # Update cached session
                await self._cache_session(session)
                
                return {
                    'success': True,
                    'session': session.__dict__,
                    'message': f'Cast control "{action}" executed successfully'
                }
            else:
                return control_result
            
        except Exception as e:
            logger.error(f"Failed to control cast session {session_id}: {e}")
            return {
                'success': False,
                'message': f'Control failed: {str(e)}'
            }
    
    async def stop_cast(self, session_id: str) -> Dict[str, Any]:
        """Stop active cast session"""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                session = await self._get_cached_session(session_id)
                
            if not session:
                return {
                    'success': False,
                    'message': 'Cast session not found'
                }
            
            device = self.discovered_devices.get(session.device_id)
            if device:
                # Send stop command to device
                await self._stop_cast_session(device, session)
            
            # Clean up session
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            await self._remove_cached_session(session_id)
            
            logger.info(f"Stopped cast session {session_id}")
            
            return {
                'success': True,
                'message': 'Cast session stopped successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to stop cast session {session_id}: {e}")
            return {
                'success': False,
                'message': f'Stop failed: {str(e)}'
            }
    
    async def get_active_sessions(self) -> List[CastSession]:
        """Get list of active cast sessions"""
        try:
            # Update from cache
            cached_sessions = await self._get_all_cached_sessions()
            
            # Filter for active sessions (updated within last 5 minutes)
            active_sessions = []
            for session in cached_sessions:
                if (datetime.now() - session.last_update).total_seconds() < 300:
                    active_sessions.append(session)
                    self.active_sessions[session.session_id] = session
            
            return active_sessions
            
        except Exception as e:
            logger.error(f"Failed to get active sessions: {e}")
            return []
    
    async def _discover_chromecast_devices(self) -> List[CastDevice]:
        """Discover Chromecast devices using mDNS"""
        try:
            # Simplified Chromecast discovery
            # In reality, you'd use proper mDNS/Zeroconf discovery
            devices = []
            
            # This is a placeholder - real implementation would use:
            # - python-zeroconf for mDNS discovery
            # - pychromecast for Chromecast communication
            
            logger.debug("Chromecast discovery completed (placeholder)")
            return devices
            
        except Exception as e:
            logger.error(f"Failed to discover Chromecast devices: {e}")
            return []
    
    async def _discover_dlna_devices(self) -> List[CastDevice]:
        """Discover DLNA/UPnP devices"""
        try:
            devices = []
            
            # SSDP (Simple Service Discovery Protocol) discovery
            # This is a simplified version
            ssdp_request = (
                "M-SEARCH * HTTP/1.1\r\n"
                "HOST: 239.255.255.250:1900\r\n"
                "MAN: \"ssdp:discover\"\r\n"
                "ST: upnp:rootdevice\r\n"
                "MX: 3\r\n\r\n"
            )
            
            try:
                # Create UDP socket for SSDP
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(3.0)
                
                # Send SSDP M-SEARCH
                sock.sendto(ssdp_request.encode('utf-8'), ('239.255.255.250', 1900))
                
                # Listen for responses
                responses = []
                try:
                    while True:
                        data, addr = sock.recvfrom(1024)
                        responses.append((data.decode('utf-8'), addr))
                except socket.timeout:
                    pass
                
                sock.close()
                
                # Parse SSDP responses
                for response, addr in responses:
                    device = await self._parse_ssdp_response(response, addr)
                    if device:
                        devices.append(device)
                
                logger.info(f"Discovered {len(devices)} DLNA/UPnP devices")
                
            except Exception as e:
                logger.error(f"SSDP discovery failed: {e}")
            
            return devices
            
        except Exception as e:
            logger.error(f"Failed to discover DLNA devices: {e}")
            return []
    
    async def _discover_apple_tv_devices(self) -> List[CastDevice]:
        """Discover Apple TV devices"""
        try:
            devices = []
            
            # Apple TV discovery would use Bonjour/mDNS
            # Looking for _airplay._tcp services
            # This is a placeholder implementation
            
            logger.debug("Apple TV discovery completed (placeholder)")
            return devices
            
        except Exception as e:
            logger.error(f"Failed to discover Apple TV devices: {e}")
            return []
    
    async def _discover_smart_tv_devices(self) -> List[CastDevice]:
        """Discover smart TV devices"""
        try:
            devices = []
            
            # Smart TV discovery would look for various protocols:
            # - Samsung Smart TVs (SSDP)
            # - LG Smart TVs (WebOS)
            # - Android TV (Chromecast built-in)
            # This is a placeholder implementation
            
            logger.debug("Smart TV discovery completed (placeholder)")
            return devices
            
        except Exception as e:
            logger.error(f"Failed to discover smart TV devices: {e}")
            return []
    
    async def _parse_ssdp_response(self, response: str, addr: Tuple[str, int]) -> Optional[CastDevice]:
        """Parse SSDP response to extract device info"""
        try:
            lines = response.split('\r\n')
            headers = {}
            
            for line in lines[1:]:  # Skip first line (status)
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip().upper()] = value.strip()
            
            # Check if it's a media renderer
            st = headers.get('ST', '')
            if 'MediaRenderer' not in st and 'AVTransport' not in st:
                return None
            
            # Extract device information
            location = headers.get('LOCATION')
            if not location:
                return None
            
            # Parse location URL to get device details
            parsed_url = urlparse(location)
            device_ip = parsed_url.hostname
            device_port = parsed_url.port or 80
            
            # Generate device ID
            device_id = f"dlna_{device_ip}_{device_port}"
            
            # Get device description (simplified)
            device_name = f"DLNA Device ({device_ip})"
            
            device = CastDevice(
                device_id=device_id,
                name=device_name,
                device_type=CastDeviceType.DLNA_DMR,
                ip_address=device_ip,
                port=device_port,
                capabilities=['play', 'pause', 'stop', 'seek'],
                manufacturer="Unknown",
                model="DLNA Renderer",
                is_available=True,
                last_seen=datetime.now(),
                supported_formats=self.supported_video_formats,
                max_resolution="1080p"
            )
            
            return device
            
        except Exception as e:
            logger.error(f"Failed to parse SSDP response: {e}")
            return None
    
    async def _get_video_streaming_info(self, video_id: int, quality: str = None) -> Optional[StreamingInfo]:
        """Get video streaming information"""
        try:
            async with get_async_session() as session:
                query = select(Video).where(Video.id == video_id).options(selectinload(Video.artist))
                result = await session.execute(query)
                video = result.scalar_one_or_none()
                
                if not video:
                    return None
                
                # Generate streaming URL
                quality = quality or self.default_quality
                stream_url = f"http://{self.server_host}:{self.server_port}/api/stream/video/{video_id}/{quality}"
                thumbnail_url = f"http://{self.server_host}:{self.server_port}/api/thumbnails/video/{video_id}"
                
                return StreamingInfo(
                    video_id=video.id,
                    stream_url=stream_url,
                    thumbnail_url=thumbnail_url,
                    title=video.title or "Unknown Title",
                    artist=video.artist_name or "Unknown Artist",
                    duration=video.duration or 0,
                    quality=quality,
                    format="mp4",
                    bitrate=self._get_bitrate_for_quality(quality)
                )
                
        except Exception as e:
            logger.error(f"Failed to get video streaming info for {video_id}: {e}")
            return None
    
    def _get_bitrate_for_quality(self, quality: str) -> int:
        """Get bitrate for video quality"""
        bitrate_map = {
            '480p': 1000,   # 1Mbps
            '720p': 2500,   # 2.5Mbps
            '1080p': 5000   # 5Mbps
        }
        return bitrate_map.get(quality, 2500)
    
    async def _start_cast_session(
        self,
        device: CastDevice,
        session: CastSession,
        streaming_info: StreamingInfo
    ) -> Dict[str, Any]:
        """Start casting session based on device type"""
        try:
            if device.device_type == CastDeviceType.DLNA_DMR:
                return await self._start_dlna_cast(device, session, streaming_info)
            elif device.device_type == CastDeviceType.CHROMECAST:
                return await self._start_chromecast_cast(device, session, streaming_info)
            elif device.device_type == CastDeviceType.APPLE_TV:
                return await self._start_airplay_cast(device, session, streaming_info)
            else:
                return {
                    'success': False,
                    'message': f'Unsupported device type: {device.device_type.value}'
                }
                
        except Exception as e:
            logger.error(f"Failed to start cast session: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def _start_dlna_cast(
        self,
        device: CastDevice,
        session: CastSession,
        streaming_info: StreamingInfo
    ) -> Dict[str, Any]:
        """Start DLNA cast session"""
        try:
            # DLNA casting using UPnP AVTransport
            # This is a simplified implementation
            
            # SOAP request to set media URI
            soap_action = "urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"
            soap_body = f"""<?xml version="1.0"?>
            <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
                        s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                <s:Body>
                    <u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                        <InstanceID>0</InstanceID>
                        <CurrentURI>{streaming_info.stream_url}</CurrentURI>
                        <CurrentURIMetaData>&lt;DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"&gt;
                            &lt;item id="1" parentID="0" restricted="1"&gt;
                                &lt;dc:title xmlns:dc="http://purl.org/dc/elements/1.1/"&gt;{streaming_info.title}&lt;/dc:title&gt;
                                &lt;dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/"&gt;{streaming_info.artist}&lt;/dc:creator&gt;
                                &lt;upnp:class xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"&gt;object.item.videoItem&lt;/upnp:class&gt;
                                &lt;res protocolInfo="http-get:*:video/mp4:*"&gt;{streaming_info.stream_url}&lt;/res&gt;
                            &lt;/item&gt;
                        &lt;/DIDL-Lite&gt;</CurrentURIMetaData>
                    </u:SetAVTransportURI>
                </s:Body>
            </s:Envelope>"""
            
            # Send SOAP request (placeholder - would use actual HTTP client)
            logger.info(f"DLNA cast started to {device.name} (placeholder)")
            session.state = CastState.CONNECTED
            
            return {
                'success': True,
                'message': 'DLNA cast started successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to start DLNA cast: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def _start_chromecast_cast(
        self,
        device: CastDevice,
        session: CastSession,
        streaming_info: StreamingInfo
    ) -> Dict[str, Any]:
        """Start Chromecast cast session"""
        try:
            # Chromecast casting would use the Cast SDK
            # This is a placeholder implementation
            logger.info(f"Chromecast cast started to {device.name} (placeholder)")
            session.state = CastState.CONNECTED
            
            return {
                'success': True,
                'message': 'Chromecast cast started successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to start Chromecast cast: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def _start_airplay_cast(
        self,
        device: CastDevice,
        session: CastSession,
        streaming_info: StreamingInfo
    ) -> Dict[str, Any]:
        """Start AirPlay cast session"""
        try:
            # AirPlay casting would use the AirPlay protocol
            # This is a placeholder implementation
            logger.info(f"AirPlay cast started to {device.name} (placeholder)")
            session.state = CastState.CONNECTED
            
            return {
                'success': True,
                'message': 'AirPlay cast started successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to start AirPlay cast: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def _execute_cast_control(
        self,
        device: CastDevice,
        session: CastSession,
        action: str,
        value: Any
    ) -> Dict[str, Any]:
        """Execute cast control command"""
        try:
            # Control commands based on device type
            logger.info(f"Executing cast control '{action}' on {device.name} (placeholder)")
            
            return {
                'success': True,
                'message': f'Cast control "{action}" executed'
            }
            
        except Exception as e:
            logger.error(f"Failed to execute cast control: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def _stop_cast_session(self, device: CastDevice, session: CastSession):
        """Stop cast session on device"""
        try:
            # Send stop command based on device type
            logger.info(f"Stopping cast session on {device.name} (placeholder)")
            session.state = CastState.DISCONNECTED
            
        except Exception as e:
            logger.error(f"Failed to stop cast session: {e}")
    
    async def _start_device_discovery(self):
        """Background task for continuous device discovery"""
        while True:
            try:
                await self.discover_devices()
                await asyncio.sleep(self.discovery_interval)
                
            except Exception as e:
                logger.error(f"Device discovery task failed: {e}")
                await asyncio.sleep(self.discovery_interval)
    
    async def _start_dlna_server(self):
        """Start DLNA/UPnP media server"""
        try:
            # This would start a UPnP media server
            # For now, it's a placeholder
            logger.info("DLNA/UPnP media server started (placeholder)")
            
        except Exception as e:
            logger.error(f"Failed to start DLNA server: {e}")
    
    async def _cache_device(self, device: CastDevice):
        """Cache device information"""
        try:
            cache_key = f"cast_device:{device.device_id}"
            device_data = {
                'device_id': device.device_id,
                'name': device.name,
                'device_type': device.device_type.value,
                'ip_address': device.ip_address,
                'port': device.port,
                'capabilities': device.capabilities,
                'manufacturer': device.manufacturer,
                'model': device.model,
                'is_available': device.is_available,
                'last_seen': device.last_seen.isoformat(),
                'supported_formats': device.supported_formats,
                'max_resolution': device.max_resolution
            }
            
            await self.redis_client.setex(cache_key, self.device_timeout, json.dumps(device_data))
            await self.redis_client.sadd("cast_devices", device.device_id)
            
        except Exception as e:
            logger.error(f"Failed to cache device {device.device_id}: {e}")
    
    async def _get_cached_device(self, device_id: str) -> Optional[CastDevice]:
        """Get cached device"""
        try:
            cache_key = f"cast_device:{device_id}"
            device_data = await self.redis_client.get(cache_key)
            
            if device_data:
                data = json.loads(device_data)
                return CastDevice(
                    device_id=data['device_id'],
                    name=data['name'],
                    device_type=CastDeviceType(data['device_type']),
                    ip_address=data['ip_address'],
                    port=data['port'],
                    capabilities=data['capabilities'],
                    manufacturer=data['manufacturer'],
                    model=data['model'],
                    is_available=data['is_available'],
                    last_seen=datetime.fromisoformat(data['last_seen']),
                    supported_formats=data['supported_formats'],
                    max_resolution=data['max_resolution']
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached device {device_id}: {e}")
            return None
    
    async def _get_cached_devices(self) -> List[CastDevice]:
        """Get all cached devices"""
        try:
            device_ids = await self.redis_client.smembers("cast_devices")
            devices = []
            
            for device_id in device_ids:
                device = await self._get_cached_device(device_id)
                if device:
                    devices.append(device)
            
            return devices
            
        except Exception as e:
            logger.error(f"Failed to get cached devices: {e}")
            return []
    
    async def _cleanup_old_devices(self):
        """Remove old/unavailable devices from cache"""
        try:
            device_ids = await self.redis_client.smembers("cast_devices")
            
            for device_id in device_ids:
                device = await self._get_cached_device(device_id)
                if not device or (datetime.now() - device.last_seen).total_seconds() > self.device_timeout * 2:
                    # Remove expired device
                    await self.redis_client.delete(f"cast_device:{device_id}")
                    await self.redis_client.srem("cast_devices", device_id)
            
        except Exception as e:
            logger.error(f"Failed to cleanup old devices: {e}")
    
    async def _cache_session(self, session: CastSession):
        """Cache cast session"""
        try:
            cache_key = f"cast_session:{session.session_id}"
            session_data = {
                'session_id': session.session_id,
                'device_id': session.device_id,
                'device_name': session.device_name,
                'video_id': session.video_id,
                'playlist_id': session.playlist_id,
                'state': session.state.value,
                'position_seconds': session.position_seconds,
                'duration_seconds': session.duration_seconds,
                'volume_level': session.volume_level,
                'is_muted': session.is_muted,
                'started_at': session.started_at.isoformat(),
                'last_update': session.last_update.isoformat(),
                'media_url': session.media_url,
                'media_title': session.media_title,
                'media_artist': session.media_artist
            }
            
            await self.redis_client.setex(cache_key, 3600, json.dumps(session_data))
            await self.redis_client.sadd("cast_sessions", session.session_id)
            
        except Exception as e:
            logger.error(f"Failed to cache session {session.session_id}: {e}")
    
    async def _get_cached_session(self, session_id: str) -> Optional[CastSession]:
        """Get cached cast session"""
        try:
            cache_key = f"cast_session:{session_id}"
            session_data = await self.redis_client.get(cache_key)
            
            if session_data:
                data = json.loads(session_data)
                return CastSession(
                    session_id=data['session_id'],
                    device_id=data['device_id'],
                    device_name=data['device_name'],
                    video_id=data.get('video_id'),
                    playlist_id=data.get('playlist_id'),
                    state=CastState(data['state']),
                    position_seconds=data['position_seconds'],
                    duration_seconds=data['duration_seconds'],
                    volume_level=data['volume_level'],
                    is_muted=data['is_muted'],
                    started_at=datetime.fromisoformat(data['started_at']),
                    last_update=datetime.fromisoformat(data['last_update']),
                    media_url=data['media_url'],
                    media_title=data['media_title'],
                    media_artist=data['media_artist']
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached session {session_id}: {e}")
            return None
    
    async def _get_all_cached_sessions(self) -> List[CastSession]:
        """Get all cached cast sessions"""
        try:
            session_ids = await self.redis_client.smembers("cast_sessions")
            sessions = []
            
            for session_id in session_ids:
                session = await self._get_cached_session(session_id)
                if session:
                    sessions.append(session)
            
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get all cached sessions: {e}")
            return []
    
    async def _remove_cached_session(self, session_id: str):
        """Remove cached cast session"""
        try:
            cache_key = f"cast_session:{session_id}"
            await self.redis_client.delete(cache_key)
            await self.redis_client.srem("cast_sessions", session_id)
            
        except Exception as e:
            logger.error(f"Failed to remove cached session {session_id}: {e}")

# Global service instance
_smart_home_service = None

async def get_smart_home_integration_service(config: Optional[Dict] = None) -> SmartHomeIntegrationService:
    """Get global smart home integration service instance"""
    global _smart_home_service
    
    if _smart_home_service is None:
        _smart_home_service = SmartHomeIntegrationService(config)
        await _smart_home_service.initialize()
    
    return _smart_home_service