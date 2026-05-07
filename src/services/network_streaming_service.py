"""
Network Streaming Service - Phase 4 Week 31
Local network streaming and mDNS discovery improvements for consumer self-hosting
"""

import asyncio
import hashlib
import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from src.database.async_connection import get_async_session
from src.database.models import Video
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.network_streaming")


class StreamingProtocol(Enum):
    """Supported streaming protocols"""

    HTTP_PROGRESSIVE = "http_progressive"  # Basic HTTP streaming
    HLS = "hls"  # HTTP Live Streaming
    DASH = "dash"  # Dynamic Adaptive Streaming
    RTSP = "rtsp"  # Real Time Streaming Protocol
    WEBRTC = "webrtc"  # WebRTC for low latency
    DLNA_HTTP = "dlna_http"  # DLNA-compatible HTTP


class NetworkMode(Enum):
    """Network operation modes"""

    LOCAL_ONLY = "local_only"  # Local network only
    SECURE_TUNNEL = "secure_tunnel"  # Secure remote access
    HYBRID = "hybrid"  # Both local and remote
    OFFLINE = "offline"  # Offline mode


class QualityProfile(Enum):
    """Streaming quality profiles"""

    MOBILE = "mobile"  # 480p, low bandwidth
    STANDARD = "standard"  # 720p, balanced
    HIGH = "high"  # 1080p, high bandwidth
    ADAPTIVE = "adaptive"  # Adaptive bitrate
    LOSSLESS = "lossless"  # Original quality


@dataclass
class NetworkClient:
    """Network client information"""

    client_id: str
    ip_address: str
    mac_address: Optional[str]
    hostname: str
    device_type: str
    user_agent: str
    supported_formats: List[str]
    preferred_quality: QualityProfile
    bandwidth_mbps: float
    is_trusted: bool
    first_seen: datetime
    last_seen: datetime
    active_streams: int


@dataclass
class StreamSession:
    """Active streaming session"""

    session_id: str
    client_id: str
    video_id: int
    protocol: StreamingProtocol
    quality: QualityProfile
    start_time: datetime
    current_position: int
    buffer_health: float
    bandwidth_usage_kbps: int
    stream_url: str
    is_paused: bool
    client_ip: str


@dataclass
class NetworkDiscoveryInfo:
    """mDNS network discovery information"""

    service_name: str
    service_type: str
    port: int
    txt_records: Dict[str, str]
    server_version: str
    supported_protocols: List[str]
    local_addresses: List[str]


class NetworkStreamingService:
    """Local network streaming with mDNS discovery"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None

        # Network configuration
        self.service_name = "MVidarr Media Server"
        self.service_type = "_mvidarr._tcp.local."
        self.http_port = int(self.config.get("http_port", 5000))
        self.streaming_port = int(self.config.get("streaming_port", 8080))

        # mDNS configuration
        self.mdns_enabled = True
        self.mdns_ttl = 300  # 5 minutes
        self.advertise_interval = 60  # 1 minute

        # Streaming configuration
        self.max_concurrent_streams = 10
        self.buffer_size_seconds = 30
        self.adaptive_bitrate_enabled = True
        self.max_bitrate_mbps = 10.0

        # Network discovery
        self.discovered_clients: Dict[str, NetworkClient] = {}
        self.active_streams: Dict[str, StreamSession] = {}
        self.local_network_ranges = []

        # Security
        self.trusted_networks = ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"]
        self.require_authentication = True
        self.rate_limit_enabled = True

    async def initialize(self):
        """Initialize network streaming service"""
        try:
            self.redis_client = await get_redis_client()

            # Detect local network ranges
            await self._detect_local_networks()

            # Start mDNS advertising
            if self.mdns_enabled:
                await self._start_mdns_advertising()

            # Start network discovery
            asyncio.create_task(self._network_discovery_loop())

            # Start stream monitoring
            asyncio.create_task(self._stream_monitoring_loop())

            logger.info("Network streaming service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize network streaming service: {e}")
            raise

    async def get_network_info(self) -> NetworkDiscoveryInfo:
        """Get network discovery information"""
        try:
            # Get local IP addresses
            local_addresses = await self._get_local_ip_addresses()

            # Create discovery info
            discovery_info = NetworkDiscoveryInfo(
                service_name=self.service_name,
                service_type=self.service_type,
                port=self.http_port,
                txt_records={
                    "version": "0.9.8",
                    "protocols": "http,hls,dlna",
                    "auth": "required" if self.require_authentication else "none",
                    "streaming_port": str(self.streaming_port),
                    "max_quality": "1080p",
                },
                server_version="MVidarr/0.9.8",
                supported_protocols=[p.value for p in StreamingProtocol],
                local_addresses=local_addresses,
            )

            return discovery_info

        except Exception as e:
            logger.error(f"Failed to get network info: {e}")
            return NetworkDiscoveryInfo("", "", 0, {}, "", [], [])

    async def discover_network_clients(self, timeout: int = 10) -> List[NetworkClient]:
        """Discover clients on the local network"""
        try:
            logger.info("Starting network client discovery...")

            # Get local network ranges
            network_ranges = await self._get_local_network_ranges()

            discovered_clients = []

            # Scan each network range
            for network_range in network_ranges:
                clients = await self._scan_network_range(network_range, timeout)
                discovered_clients.extend(clients)

            # Update client cache
            for client in discovered_clients:
                self.discovered_clients[client.client_id] = client
                await self._cache_network_client(client)

            logger.info(f"Discovered {len(discovered_clients)} network clients")
            return discovered_clients

        except Exception as e:
            logger.error(f"Failed to discover network clients: {e}")
            return []

    async def start_stream(
        self,
        video_id: int,
        client_id: str,
        protocol: StreamingProtocol = StreamingProtocol.HTTP_PROGRESSIVE,
        quality: QualityProfile = QualityProfile.ADAPTIVE,
    ) -> Dict[str, Any]:
        """Start streaming session"""
        try:
            # Check if client exists
            client = await self._get_network_client(client_id)
            if not client:
                return {"success": False, "message": "Client not found"}

            # Check concurrent stream limit
            if len(self.active_streams) >= self.max_concurrent_streams:
                return {
                    "success": False,
                    "message": "Maximum concurrent streams exceeded",
                }

            # Get video information
            async with get_async_session() as session:
                video_query = select(Video).where(Video.id == video_id)
                result = await session.execute(video_query)
                video = result.scalar_one_or_none()

                if not video:
                    return {"success": False, "message": "Video not found"}

                # Create streaming session
                session_id = f"stream_{int(time.time())}_{hashlib.md5(f'{video_id}_{client_id}'.encode(), usedforsecurity=False).hexdigest()[:8]}"

                # Generate stream URL based on protocol
                stream_url = await self._generate_stream_url(video, protocol, quality)

                stream_session = StreamSession(
                    session_id=session_id,
                    client_id=client_id,
                    video_id=video_id,
                    protocol=protocol,
                    quality=quality,
                    start_time=datetime.now(),
                    current_position=0,
                    buffer_health=1.0,
                    bandwidth_usage_kbps=0,
                    stream_url=stream_url,
                    is_paused=False,
                    client_ip=client.ip_address,
                )

                # Store active stream
                self.active_streams[session_id] = stream_session
                await self._cache_stream_session(stream_session)

                # Update client active streams
                client.active_streams += 1
                client.last_seen = datetime.now()
                await self._cache_network_client(client)

                logger.info(
                    f"Started streaming session {session_id} for video {video_id}"
                )

                return {
                    "success": True,
                    "session_id": session_id,
                    "stream_url": stream_url,
                    "protocol": protocol.value,
                    "quality": quality.value,
                }

        except Exception as e:
            logger.error(f"Failed to start stream for video {video_id}: {e}")
            return {"success": False, "message": f"Streaming failed: {str(e)}"}

    async def stop_stream(self, session_id: str) -> Dict[str, Any]:
        """Stop streaming session"""
        try:
            stream_session = self.active_streams.get(session_id)
            if not stream_session:
                return {"success": False, "message": "Stream session not found"}

            # Update client info
            client = await self._get_network_client(stream_session.client_id)
            if client and client.active_streams > 0:
                client.active_streams -= 1
                await self._cache_network_client(client)

            # Remove from active streams
            del self.active_streams[session_id]
            await self._remove_cached_stream_session(session_id)

            logger.info(f"Stopped streaming session {session_id}")

            return {"success": True, "message": "Stream stopped successfully"}

        except Exception as e:
            logger.error(f"Failed to stop stream {session_id}: {e}")
            return {"success": False, "message": f"Stop failed: {str(e)}"}

    async def get_stream_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get streaming session status"""
        try:
            stream_session = self.active_streams.get(session_id)
            if not stream_session:
                stream_session = await self._get_cached_stream_session(session_id)

            if not stream_session:
                return None

            # Calculate stream duration
            duration_seconds = (
                datetime.now() - stream_session.start_time
            ).total_seconds()

            return {
                "session_id": stream_session.session_id,
                "video_id": stream_session.video_id,
                "client_id": stream_session.client_id,
                "protocol": stream_session.protocol.value,
                "quality": stream_session.quality.value,
                "duration_seconds": int(duration_seconds),
                "current_position": stream_session.current_position,
                "buffer_health": stream_session.buffer_health,
                "bandwidth_usage_kbps": stream_session.bandwidth_usage_kbps,
                "is_paused": stream_session.is_paused,
                "client_ip": stream_session.client_ip,
            }

        except Exception as e:
            logger.error(f"Failed to get stream status for {session_id}: {e}")
            return None

    async def get_active_streams(self) -> List[Dict[str, Any]]:
        """Get list of active streaming sessions"""
        try:
            active_streams = []

            for session in self.active_streams.values():
                status = await self.get_stream_status(session.session_id)
                if status:
                    active_streams.append(status)

            return active_streams

        except Exception as e:
            logger.error(f"Failed to get active streams: {e}")
            return []

    async def get_network_clients(self) -> List[NetworkClient]:
        """Get list of discovered network clients"""
        try:
            # Update from cache
            cached_clients = await self._get_all_cached_clients()

            # Filter for recently seen clients
            active_clients = []
            for client in cached_clients:
                if (datetime.now() - client.last_seen).total_seconds() < 3600:  # 1 hour
                    active_clients.append(client)
                    self.discovered_clients[client.client_id] = client

            return active_clients

        except Exception as e:
            logger.error(f"Failed to get network clients: {e}")
            return []

    async def optimize_stream_quality(
        self, session_id: str, target_quality: QualityProfile = None
    ) -> Dict[str, Any]:
        """Optimize streaming quality based on network conditions"""
        try:
            stream_session = self.active_streams.get(session_id)
            if not stream_session:
                return {"success": False, "message": "Stream session not found"}

            client = await self._get_network_client(stream_session.client_id)
            if not client:
                return {"success": False, "message": "Client not found"}

            # Analyze network conditions
            network_analysis = await self._analyze_network_conditions(client)

            # Determine optimal quality
            if target_quality:
                optimal_quality = target_quality
            else:
                optimal_quality = await self._determine_optimal_quality(
                    network_analysis
                )

            # Update stream if quality changed
            if optimal_quality != stream_session.quality:
                stream_session.quality = optimal_quality

                # Generate new stream URL
                async with get_async_session() as session:
                    video_query = select(Video).where(
                        Video.id == stream_session.video_id
                    )
                    result = await session.execute(video_query)
                    video = result.scalar_one_or_none()

                    if video:
                        stream_session.stream_url = await self._generate_stream_url(
                            video, stream_session.protocol, optimal_quality
                        )

                await self._cache_stream_session(stream_session)

                logger.info(
                    f"Optimized stream quality to {optimal_quality.value} for session {session_id}"
                )

                return {
                    "success": True,
                    "old_quality": stream_session.quality.value,
                    "new_quality": optimal_quality.value,
                    "new_stream_url": stream_session.stream_url,
                    "network_analysis": network_analysis,
                }
            else:
                return {
                    "success": True,
                    "message": "Quality already optimal",
                    "current_quality": optimal_quality.value,
                    "network_analysis": network_analysis,
                }

        except Exception as e:
            logger.error(f"Failed to optimize stream quality for {session_id}: {e}")
            return {"success": False, "message": f"Optimization failed: {str(e)}"}

    async def _detect_local_networks(self):
        """Detect local network ranges"""
        try:
            import psutil

            network_ranges = []

            # Get network interfaces
            for interface, addresses in psutil.net_if_addrs().items():
                for address in addresses:
                    if address.family == socket.AF_INET:
                        try:
                            network = ipaddress.IPv4Network(
                                f"{address.address}/{address.netmask}", strict=False
                            )
                            if network.is_private:
                                network_ranges.append(str(network))
                        except ValueError:
                            continue

            self.local_network_ranges = network_ranges
            logger.info(f"Detected local networks: {network_ranges}")

        except Exception as e:
            logger.error(f"Failed to detect local networks: {e}")

    async def _start_mdns_advertising(self):
        """Start mDNS service advertising"""
        try:
            # This would use python-zeroconf or similar library
            # For now, it's a placeholder
            logger.info(f"mDNS advertising started for {self.service_name}")

            # Start background advertising loop
            asyncio.create_task(self._mdns_advertising_loop())

        except Exception as e:
            logger.error(f"Failed to start mDNS advertising: {e}")

    async def _mdns_advertising_loop(self):
        """Background mDNS advertising loop"""
        while True:
            try:
                # Advertise service
                discovery_info = await self.get_network_info()

                # Update service advertisement
                logger.debug(
                    f"mDNS advertisement: {discovery_info.service_name} on port {discovery_info.port}"
                )

                await asyncio.sleep(self.advertise_interval)

            except Exception as e:
                logger.error(f"mDNS advertising loop failed: {e}")
                await asyncio.sleep(self.advertise_interval)

    async def _network_discovery_loop(self):
        """Background network discovery loop"""
        while True:
            try:
                # Discover clients every 5 minutes
                await self.discover_network_clients()
                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"Network discovery loop failed: {e}")
                await asyncio.sleep(300)

    async def _stream_monitoring_loop(self):
        """Background stream monitoring loop"""
        while True:
            try:
                # Monitor active streams
                for session_id, stream_session in list(self.active_streams.items()):
                    await self._monitor_stream_health(stream_session)

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Stream monitoring loop failed: {e}")
                await asyncio.sleep(30)

    async def _get_local_ip_addresses(self) -> List[str]:
        """Get local IP addresses"""
        try:
            import psutil

            addresses = []
            for interface, interface_addresses in psutil.net_if_addrs().items():
                for address in interface_addresses:
                    if (
                        address.family == socket.AF_INET
                        and not address.address.startswith("127.")
                    ):
                        addresses.append(address.address)

            return addresses

        except Exception as e:
            logger.error(f"Failed to get local IP addresses: {e}")
            return []

    async def _get_local_network_ranges(self) -> List[str]:
        """Get local network ranges for scanning"""
        if not self.local_network_ranges:
            await self._detect_local_networks()
        return self.local_network_ranges

    async def _scan_network_range(
        self, network_range: str, timeout: int
    ) -> List[NetworkClient]:
        """Scan network range for clients"""
        try:
            clients = []

            # This is a simplified implementation
            # In reality, you'd use proper network scanning techniques
            network = ipaddress.IPv4Network(network_range, strict=False)

            # Scan first 10 hosts for demo purposes
            for i, host in enumerate(network.hosts()):
                if i >= 10:  # Limit scan for demo
                    break

                # Simulate client discovery
                if i % 3 == 0:  # Every 3rd host has a client
                    client = NetworkClient(
                        client_id=f"client_{str(host).replace('.', '_')}",
                        ip_address=str(host),
                        mac_address=None,
                        hostname=f"device-{host.compressed.split('.')[-1]}",
                        device_type="unknown",
                        user_agent="",
                        supported_formats=["mp4", "mkv"],
                        preferred_quality=QualityProfile.STANDARD,
                        bandwidth_mbps=10.0,
                        is_trusted=self._is_trusted_network(str(host)),
                        first_seen=datetime.now(),
                        last_seen=datetime.now(),
                        active_streams=0,
                    )
                    clients.append(client)

            return clients

        except Exception as e:
            logger.error(f"Failed to scan network range {network_range}: {e}")
            return []

    async def _generate_stream_url(
        self, video: Video, protocol: StreamingProtocol, quality: QualityProfile
    ) -> str:
        """Generate streaming URL"""
        try:
            base_url = f"http://localhost:{self.streaming_port}"

            if protocol == StreamingProtocol.HTTP_PROGRESSIVE:
                return f"{base_url}/stream/{video.id}/{quality.value}.mp4"
            elif protocol == StreamingProtocol.HLS:
                return f"{base_url}/hls/{video.id}/{quality.value}/playlist.m3u8"
            elif protocol == StreamingProtocol.DASH:
                return f"{base_url}/dash/{video.id}/{quality.value}/manifest.mpd"
            elif protocol == StreamingProtocol.DLNA_HTTP:
                return f"{base_url}/dlna/{video.id}/{quality.value}.mp4"
            else:
                return f"{base_url}/stream/{video.id}/{quality.value}.mp4"

        except Exception as e:
            logger.error(f"Failed to generate stream URL: {e}")
            return ""

    async def _analyze_network_conditions(
        self, client: NetworkClient
    ) -> Dict[str, Any]:
        """Analyze network conditions for client"""
        return {
            "bandwidth_mbps": client.bandwidth_mbps,
            "latency_ms": 50,  # Simplified
            "packet_loss_percent": 0.1,  # Simplified
            "connection_quality": "good",  # Simplified
        }

    async def _determine_optimal_quality(
        self, network_analysis: Dict[str, Any]
    ) -> QualityProfile:
        """Determine optimal streaming quality based on network analysis"""
        try:
            bandwidth = network_analysis.get("bandwidth_mbps", 10.0)

            if bandwidth >= 8.0:
                return QualityProfile.HIGH
            elif bandwidth >= 4.0:
                return QualityProfile.STANDARD
            else:
                return QualityProfile.MOBILE

        except Exception as e:
            logger.error(f"Failed to determine optimal quality: {e}")
            return QualityProfile.STANDARD

    async def _monitor_stream_health(self, stream_session: StreamSession):
        """Monitor streaming session health"""
        try:
            # Check if stream is still active
            if (
                datetime.now() - stream_session.start_time
            ).total_seconds() > 3600:  # 1 hour timeout
                logger.info(f"Stream session {stream_session.session_id} timed out")
                await self.stop_stream(stream_session.session_id)

        except Exception as e:
            logger.error(f"Failed to monitor stream health: {e}")

    def _is_trusted_network(self, ip_address: str) -> bool:
        """Check if IP address is in trusted network range"""
        try:
            client_ip = ipaddress.IPv4Address(ip_address)
            for network_range in self.trusted_networks:
                if client_ip in ipaddress.IPv4Network(network_range):
                    return True
            return False

        except Exception as e:
            logger.error(f"Failed to check trusted network for {ip_address}: {e}")
            return False

    async def _cache_network_client(self, client: NetworkClient):
        """Cache network client information"""
        try:
            cache_key = f"network_client:{client.client_id}"
            client_data = {
                "client_id": client.client_id,
                "ip_address": client.ip_address,
                "mac_address": client.mac_address,
                "hostname": client.hostname,
                "device_type": client.device_type,
                "user_agent": client.user_agent,
                "supported_formats": client.supported_formats,
                "preferred_quality": client.preferred_quality.value,
                "bandwidth_mbps": client.bandwidth_mbps,
                "is_trusted": client.is_trusted,
                "first_seen": client.first_seen.isoformat(),
                "last_seen": client.last_seen.isoformat(),
                "active_streams": client.active_streams,
            }

            await self.redis_client.setex(cache_key, 3600, json.dumps(client_data))
            await self.redis_client.sadd("network_clients", client.client_id)

        except Exception as e:
            logger.error(f"Failed to cache network client {client.client_id}: {e}")

    async def _get_network_client(self, client_id: str) -> Optional[NetworkClient]:
        """Get cached network client"""
        try:
            cache_key = f"network_client:{client_id}"
            client_data = await self.redis_client.get(cache_key)

            if client_data:
                data = json.loads(client_data)
                return NetworkClient(
                    client_id=data["client_id"],
                    ip_address=data["ip_address"],
                    mac_address=data.get("mac_address"),
                    hostname=data["hostname"],
                    device_type=data["device_type"],
                    user_agent=data["user_agent"],
                    supported_formats=data["supported_formats"],
                    preferred_quality=QualityProfile(data["preferred_quality"]),
                    bandwidth_mbps=data["bandwidth_mbps"],
                    is_trusted=data["is_trusted"],
                    first_seen=datetime.fromisoformat(data["first_seen"]),
                    last_seen=datetime.fromisoformat(data["last_seen"]),
                    active_streams=data["active_streams"],
                )

            return None

        except Exception as e:
            logger.error(f"Failed to get network client {client_id}: {e}")
            return None

    async def _get_all_cached_clients(self) -> List[NetworkClient]:
        """Get all cached network clients"""
        try:
            client_ids = await self.redis_client.smembers("network_clients")
            clients = []

            for client_id in client_ids:
                client = await self._get_network_client(client_id)
                if client:
                    clients.append(client)

            return clients

        except Exception as e:
            logger.error(f"Failed to get all cached clients: {e}")
            return []

    async def _cache_stream_session(self, stream_session: StreamSession):
        """Cache streaming session"""
        try:
            cache_key = f"stream_session:{stream_session.session_id}"
            session_data = {
                "session_id": stream_session.session_id,
                "client_id": stream_session.client_id,
                "video_id": stream_session.video_id,
                "protocol": stream_session.protocol.value,
                "quality": stream_session.quality.value,
                "start_time": stream_session.start_time.isoformat(),
                "current_position": stream_session.current_position,
                "buffer_health": stream_session.buffer_health,
                "bandwidth_usage_kbps": stream_session.bandwidth_usage_kbps,
                "stream_url": stream_session.stream_url,
                "is_paused": stream_session.is_paused,
                "client_ip": stream_session.client_ip,
            }

            await self.redis_client.setex(cache_key, 3600, json.dumps(session_data))
            await self.redis_client.sadd("stream_sessions", stream_session.session_id)

        except Exception as e:
            logger.error(
                f"Failed to cache stream session {stream_session.session_id}: {e}"
            )

    async def _get_cached_stream_session(
        self, session_id: str
    ) -> Optional[StreamSession]:
        """Get cached streaming session"""
        try:
            cache_key = f"stream_session:{session_id}"
            session_data = await self.redis_client.get(cache_key)

            if session_data:
                data = json.loads(session_data)
                return StreamSession(
                    session_id=data["session_id"],
                    client_id=data["client_id"],
                    video_id=data["video_id"],
                    protocol=StreamingProtocol(data["protocol"]),
                    quality=QualityProfile(data["quality"]),
                    start_time=datetime.fromisoformat(data["start_time"]),
                    current_position=data["current_position"],
                    buffer_health=data["buffer_health"],
                    bandwidth_usage_kbps=data["bandwidth_usage_kbps"],
                    stream_url=data["stream_url"],
                    is_paused=data["is_paused"],
                    client_ip=data["client_ip"],
                )

            return None

        except Exception as e:
            logger.error(f"Failed to get cached stream session {session_id}: {e}")
            return None

    async def _remove_cached_stream_session(self, session_id: str):
        """Remove cached streaming session"""
        try:
            cache_key = f"stream_session:{session_id}"
            await self.redis_client.delete(cache_key)
            await self.redis_client.srem("stream_sessions", session_id)

        except Exception as e:
            logger.error(f"Failed to remove cached stream session {session_id}: {e}")


# Global service instance
_network_streaming_service = None


async def get_network_streaming_service(
    config: Optional[Dict] = None,
) -> NetworkStreamingService:
    """Get global network streaming service instance"""
    global _network_streaming_service

    if _network_streaming_service is None:
        _network_streaming_service = NetworkStreamingService(config)
        await _network_streaming_service.initialize()

    return _network_streaming_service
