"""
Local Network Sharing Service - Phase 3 Week 29
Consumer-focused home network sharing for music video collections
"""

import base64
import hashlib
import json
import os
import socket
from datetime import datetime, timedelta
from enum import Enum
from io import BytesIO
from typing import Any, Dict, List, Optional

import netifaces
import qrcode
from zeroconf import ServiceInfo, Zeroconf

from src.services.performance_monitor import get_performance_monitor
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.local_network_share")


class ShareType(Enum):
    """Types of network shares"""

    MUSIC_VIDEOS = "music_videos"
    COLLECTIONS = "collections"
    PLAYLISTS = "playlists"
    RECENT_IMPORTS = "recent_imports"
    CUSTOM_FOLDER = "custom_folder"


class AccessLevel(Enum):
    """Access levels for network shares"""

    READ_ONLY = "read_only"
    STREAMING_ONLY = "streaming_only"
    DOWNLOAD_ALLOWED = "download_allowed"


class DeviceType(Enum):
    """Types of devices on network"""

    MOBILE_PHONE = "mobile_phone"
    TABLET = "tablet"
    LAPTOP = "laptop"
    DESKTOP = "desktop"
    SMART_TV = "smart_tv"
    STREAMING_DEVICE = "streaming_device"
    UNKNOWN = "unknown"


class NetworkDevice:
    """Represents a device on the local network"""

    def __init__(self, ip_address: str):
        self.ip_address = ip_address
        self.mac_address: Optional[str] = None
        self.hostname: Optional[str] = None
        self.device_name: Optional[str] = None
        self.device_type = DeviceType.UNKNOWN
        self.user_agent: Optional[str] = None
        self.last_seen: datetime = datetime.now()
        self.access_level = AccessLevel.READ_ONLY
        self.is_trusted: bool = False
        self.bandwidth_used: int = 0
        self.files_accessed: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "hostname": self.hostname,
            "device_name": self.device_name,
            "device_type": self.device_type.value,
            "user_agent": self.user_agent,
            "last_seen": self.last_seen.isoformat(),
            "access_level": self.access_level.value,
            "is_trusted": self.is_trusted,
            "bandwidth_used": self.bandwidth_used,
            "files_accessed_count": len(self.files_accessed),
        }


class NetworkShare:
    """Represents a network share configuration"""

    def __init__(self, share_id: str):
        self.share_id = share_id
        self.name: str = ""
        self.share_type = ShareType.MUSIC_VIDEOS
        self.local_path: str = ""
        self.access_level = AccessLevel.STREAMING_ONLY
        self.enabled: bool = True
        self.password_protected: bool = False
        self.password_hash: Optional[str] = None
        self.allowed_devices: List[str] = []  # IP addresses or MAC addresses
        self.max_concurrent_users: int = 5
        self.bandwidth_limit_mbps: Optional[int] = None
        self.created_at: datetime = datetime.now()
        self.access_count: int = 0
        self.last_accessed: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "share_id": self.share_id,
            "name": self.name,
            "share_type": self.share_type.value,
            "local_path": self.local_path,
            "access_level": self.access_level.value,
            "enabled": self.enabled,
            "password_protected": self.password_protected,
            "allowed_devices": self.allowed_devices,
            "max_concurrent_users": self.max_concurrent_users,
            "bandwidth_limit_mbps": self.bandwidth_limit_mbps,
            "created_at": self.created_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": (
                self.last_accessed.isoformat() if self.last_accessed else None
            ),
        }


class LocalNetworkShareService:
    """Consumer-focused local network sharing service"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.performance_monitor = None
        self.zeroconf = None
        self.service_info = None

        # Network configuration
        self.server_host = "0.0.0.0"
        self.server_port = self.config.get("share_port", 8090)
        self.service_name = self.config.get("service_name", "MVidarr Media Server")

        # Consumer-friendly settings
        self.max_concurrent_streams = 10
        self.max_file_size_mb = 2048  # 2GB limit for consumer networks
        self.chunk_size_kb = 64  # 64KB chunks for streaming
        self.discovery_interval = 300  # 5 minutes

        # Active shares and devices
        self.active_shares: Dict[str, NetworkShare] = {}
        self.connected_devices: Dict[str, NetworkDevice] = {}
        self.active_streams: Dict[str, Dict] = {}

        # Network discovery
        self.local_ip = self._get_local_ip()
        self.network_interfaces = self._get_network_interfaces()

    async def initialize(self):
        """Initialize network sharing service"""
        try:
            self.redis_client = await get_redis_client()
            self.performance_monitor = await get_performance_monitor()

            # Load existing shares
            await self._load_saved_shares()

            # Start network discovery
            await self._start_network_discovery()

            # Register mDNS service for easy discovery
            await self._register_mdns_service()

            logger.info(
                f"Local network sharing service initialized on {self.local_ip}:{self.server_port}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize network sharing service: {e}")
            raise

    async def create_share(
        self,
        name: str,
        share_type: ShareType,
        local_path: str,
        access_level: AccessLevel = AccessLevel.STREAMING_ONLY,
        options: Optional[Dict] = None,
    ) -> NetworkShare:
        """Create a new network share"""
        try:
            # Validate local path exists
            if not os.path.exists(local_path):
                raise ValueError(f"Local path does not exist: {local_path}")

            # Generate share ID
            share_id = f"share_{hashlib.md5(f'{name}_{local_path}'.encode(), usedforsecurity=False).hexdigest()[:12]}"

            # Create share
            share = NetworkShare(share_id)
            share.name = name
            share.share_type = share_type
            share.local_path = local_path
            share.access_level = access_level

            # Apply options
            if options:
                share.password_protected = options.get("password_protected", False)
                if share.password_protected and options.get("password"):
                    share.password_hash = hashlib.sha256(
                        options["password"].encode()
                    ).hexdigest()

                share.max_concurrent_users = options.get("max_concurrent_users", 5)
                share.bandwidth_limit_mbps = options.get("bandwidth_limit_mbps")
                share.allowed_devices = options.get("allowed_devices", [])

            # Store share
            self.active_shares[share_id] = share
            await self._save_share(share)

            logger.info(f"Created network share '{name}' ({share_id}) for {local_path}")

            return share

        except Exception as e:
            logger.error(f"Failed to create network share: {e}")
            raise

    async def update_share(self, share_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing network share"""
        try:
            if share_id not in self.active_shares:
                raise ValueError(f"Share {share_id} not found")

            share = self.active_shares[share_id]

            # Update share properties
            for key, value in updates.items():
                if key == "name":
                    share.name = value
                elif key == "access_level":
                    share.access_level = AccessLevel(value)
                elif key == "enabled":
                    share.enabled = bool(value)
                elif key == "password_protected":
                    share.password_protected = bool(value)
                elif key == "password" and value:
                    share.password_hash = hashlib.sha256(value.encode()).hexdigest()
                elif key == "max_concurrent_users":
                    share.max_concurrent_users = int(value)
                elif key == "bandwidth_limit_mbps":
                    share.bandwidth_limit_mbps = int(value) if value else None
                elif key == "allowed_devices":
                    share.allowed_devices = list(value) if value else []

            await self._save_share(share)

            logger.info(f"Updated network share {share_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to update share {share_id}: {e}")
            return False

    async def delete_share(self, share_id: str) -> bool:
        """Delete a network share"""
        try:
            if share_id not in self.active_shares:
                raise ValueError(f"Share {share_id} not found")

            # Remove from active shares
            del self.active_shares[share_id]

            # Remove from Redis
            await self.redis_client.delete(f"network_share:{share_id}")

            logger.info(f"Deleted network share {share_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to delete share {share_id}: {e}")
            return False

    async def list_shares(self) -> List[Dict[str, Any]]:
        """List all network shares"""
        try:
            shares = []
            for share in self.active_shares.values():
                share_dict = share.to_dict()

                # Add runtime information
                share_dict["current_users"] = self._get_share_user_count(share.share_id)
                share_dict["is_accessible"] = os.path.exists(share.local_path)

                shares.append(share_dict)

            return shares

        except Exception as e:
            logger.error(f"Failed to list shares: {e}")
            return []

    async def get_connected_devices(self) -> List[Dict[str, Any]]:
        """Get list of connected devices on network"""
        try:
            devices = []

            # Update device discovery
            await self._update_device_discovery()

            for device in self.connected_devices.values():
                device_dict = device.to_dict()

                # Add runtime information
                device_dict["is_online"] = (
                    datetime.now() - device.last_seen
                ).seconds < 600  # 10 minutes
                device_dict["current_streams"] = self._get_device_stream_count(
                    device.ip_address
                )

                devices.append(device_dict)

            return devices

        except Exception as e:
            logger.error(f"Failed to get connected devices: {e}")
            return []

    async def generate_access_qr_code(self, share_id: str) -> Optional[str]:
        """Generate QR code for easy mobile access to share"""
        try:
            if share_id not in self.active_shares:
                raise ValueError(f"Share {share_id} not found")

            share = self.active_shares[share_id]

            # Create access URL
            access_url = f"http://{self.local_ip}:{self.server_port}/share/{share_id}"
            if share.password_protected:
                access_url += "?auth_required=true"

            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(access_url)
            qr.make(fit=True)

            # Create QR code image
            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qr_code_data = base64.b64encode(buffer.getvalue()).decode()

            logger.info(f"Generated QR code for share {share_id}")

            return qr_code_data

        except Exception as e:
            logger.error(f"Failed to generate QR code for share {share_id}: {e}")
            return None

    async def get_network_status(self) -> Dict[str, Any]:
        """Get comprehensive network sharing status"""
        try:
            # Get system performance
            if self.performance_monitor:
                system_health = (
                    await self.performance_monitor.get_system_health_summary()
                )
            else:
                system_health = {}

            status = {
                "service_name": self.service_name,
                "server_address": f"{self.local_ip}:{self.server_port}",
                "network_interfaces": self.network_interfaces,
                "total_shares": len(self.active_shares),
                "active_shares": len(
                    [s for s in self.active_shares.values() if s.enabled]
                ),
                "connected_devices": len(self.connected_devices),
                "active_streams": len(self.active_streams),
                "total_bandwidth_mbps": sum(
                    stream.get("bandwidth_mbps", 0)
                    for stream in self.active_streams.values()
                ),
                "system_health": system_health.get("overall_score", 100),
                "uptime_seconds": (
                    datetime.now() - datetime.now()
                ).total_seconds(),  # Would be actual uptime
                "discovery_enabled": bool(self.zeroconf),
                "mdns_service_registered": bool(self.service_info),
            }

            return status

        except Exception as e:
            logger.error(f"Failed to get network status: {e}")
            return {}

    async def set_device_access_level(
        self, device_ip: str, access_level: AccessLevel, trusted: bool = False
    ) -> bool:
        """Set access level for a specific device"""
        try:
            if device_ip not in self.connected_devices:
                # Create device entry
                device = NetworkDevice(device_ip)
                self.connected_devices[device_ip] = device
            else:
                device = self.connected_devices[device_ip]

            device.access_level = access_level
            device.is_trusted = trusted
            device.last_seen = datetime.now()

            # Save device info
            await self._save_device_info(device)

            logger.info(
                f"Set access level for device {device_ip} to {access_level.value}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to set device access level: {e}")
            return False

    def _get_local_ip(self) -> str:
        """Get local IP address for network sharing"""
        try:
            # Try to find the best local IP address
            interfaces = netifaces.interfaces()

            for interface in interfaces:
                if interface.startswith("lo"):  # Skip loopback
                    continue

                addresses = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addresses:
                    for addr_info in addresses[netifaces.AF_INET]:
                        ip = addr_info.get("addr")
                        if (
                            ip
                            and not ip.startswith("127.")
                            and not ip.startswith("169.254.")
                        ):
                            return ip

            # Fallback method
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]

        except Exception as e:
            logger.warning(f"Failed to get local IP: {e}")
            return "127.0.0.1"

    def _get_network_interfaces(self) -> List[Dict[str, Any]]:
        """Get available network interfaces"""
        try:
            interfaces = []

            for interface_name in netifaces.interfaces():
                if interface_name.startswith("lo"):  # Skip loopback
                    continue

                addresses = netifaces.ifaddresses(interface_name)
                if netifaces.AF_INET in addresses:
                    for addr_info in addresses[netifaces.AF_INET]:
                        ip = addr_info.get("addr")
                        if ip and not ip.startswith("127."):
                            interfaces.append(
                                {
                                    "name": interface_name,
                                    "ip_address": ip,
                                    "netmask": addr_info.get("netmask"),
                                    "broadcast": addr_info.get("broadcast"),
                                    "is_primary": ip == self.local_ip,
                                }
                            )

            return interfaces

        except Exception as e:
            logger.warning(f"Failed to get network interfaces: {e}")
            return []

    async def _start_network_discovery(self):
        """Start network device discovery"""
        try:
            # This would implement network scanning for devices
            # For consumer use, we'll use passive discovery through connection logs
            logger.info("Network discovery started (passive mode)")

        except Exception as e:
            logger.error(f"Failed to start network discovery: {e}")

    async def _register_mdns_service(self):
        """Register mDNS service for easy discovery"""
        try:
            if not self.local_ip or self.local_ip == "127.0.0.1":
                logger.warning("Cannot register mDNS service without valid local IP")
                return

            self.zeroconf = Zeroconf()

            # Service information
            service_type = "_mvidarr._tcp.local."
            service_name = f"{self.service_name.replace(' ', '-')}._mvidarr._tcp.local."

            properties = {
                b"service": b"MVidarr Media Server",
                b"version": b"1.0",
                b"shares": str(len(self.active_shares)).encode(),
                b"access": b"local_network",
            }

            self.service_info = ServiceInfo(
                service_type,
                service_name,
                addresses=[socket.inet_aton(self.local_ip)],
                port=self.server_port,
                properties=properties,
                server=f"{socket.gethostname()}.local.",
            )

            self.zeroconf.register_service(self.service_info)

            logger.info(f"Registered mDNS service: {service_name}")

        except Exception as e:
            logger.error(f"Failed to register mDNS service: {e}")

    async def _update_device_discovery(self):
        """Update device discovery information"""
        try:
            # Clean up old device entries (not seen in 24 hours)
            cutoff_time = datetime.now() - timedelta(hours=24)

            devices_to_remove = []
            for device_ip, device in self.connected_devices.items():
                if device.last_seen < cutoff_time:
                    devices_to_remove.append(device_ip)

            for device_ip in devices_to_remove:
                del self.connected_devices[device_ip]
                await self.redis_client.delete(f"network_device:{device_ip}")

            if devices_to_remove:
                logger.info(f"Cleaned up {len(devices_to_remove)} inactive devices")

        except Exception as e:
            logger.error(f"Failed to update device discovery: {e}")

    def _get_share_user_count(self, share_id: str) -> int:
        """Get current number of users accessing a share"""
        count = 0
        for stream in self.active_streams.values():
            if stream.get("share_id") == share_id:
                count += 1
        return count

    def _get_device_stream_count(self, device_ip: str) -> int:
        """Get current number of streams for a device"""
        count = 0
        for stream in self.active_streams.values():
            if stream.get("device_ip") == device_ip:
                count += 1
        return count

    async def _save_share(self, share: NetworkShare):
        """Save share configuration to Redis"""
        try:
            cache_key = f"network_share:{share.share_id}"
            await self.redis_client.setex(
                cache_key, 86400 * 30, json.dumps(share.to_dict())
            )

        except Exception as e:
            logger.error(f"Failed to save share {share.share_id}: {e}")

    async def _load_saved_shares(self):
        """Load saved shares from Redis"""
        try:
            pattern = "network_share:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys:
                try:
                    share_data = await self.redis_client.get(key)
                    if share_data:
                        share_dict = json.loads(share_data)

                        # Reconstruct NetworkShare object
                        share = NetworkShare(share_dict["share_id"])
                        share.name = share_dict.get("name", "")
                        share.share_type = ShareType(
                            share_dict.get("share_type", "music_videos")
                        )
                        share.local_path = share_dict.get("local_path", "")
                        share.access_level = AccessLevel(
                            share_dict.get("access_level", "streaming_only")
                        )
                        share.enabled = share_dict.get("enabled", True)
                        share.password_protected = share_dict.get(
                            "password_protected", False
                        )
                        share.allowed_devices = share_dict.get("allowed_devices", [])
                        share.max_concurrent_users = share_dict.get(
                            "max_concurrent_users", 5
                        )
                        share.bandwidth_limit_mbps = share_dict.get(
                            "bandwidth_limit_mbps"
                        )
                        share.access_count = share_dict.get("access_count", 0)

                        if share_dict.get("created_at"):
                            share.created_at = datetime.fromisoformat(
                                share_dict["created_at"]
                            )

                        if share_dict.get("last_accessed"):
                            share.last_accessed = datetime.fromisoformat(
                                share_dict["last_accessed"]
                            )

                        self.active_shares[share.share_id] = share

                except Exception as e:
                    logger.warning(f"Failed to load share from {key}: {e}")
                    continue

            logger.info(f"Loaded {len(self.active_shares)} saved network shares")

        except Exception as e:
            logger.error(f"Failed to load saved shares: {e}")

    async def _save_device_info(self, device: NetworkDevice):
        """Save device information to Redis"""
        try:
            cache_key = f"network_device:{device.ip_address}"
            await self.redis_client.setex(
                cache_key, 86400 * 7, json.dumps(device.to_dict())
            )

        except Exception as e:
            logger.error(f"Failed to save device info for {device.ip_address}: {e}")

    async def shutdown(self):
        """Shutdown network sharing service"""
        try:
            # Unregister mDNS service
            if self.zeroconf and self.service_info:
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()

            # Clear active streams
            self.active_streams.clear()

            logger.info("Network sharing service shutdown complete")

        except Exception as e:
            logger.error(f"Failed to shutdown network sharing service: {e}")


# Global service instance
_local_network_share = None


async def get_local_network_share(
    config: Optional[Dict] = None,
) -> LocalNetworkShareService:
    """Get global local network sharing service instance"""
    global _local_network_share

    if _local_network_share is None:
        _local_network_share = LocalNetworkShareService(config)
        await _local_network_share.initialize()

    return _local_network_share
