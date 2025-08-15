"""Time control utilities for deterministic testing."""

import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Callable
from unittest import mock
import logging

logger = logging.getLogger(__name__)


class TimeController:
    """Control time for deterministic testing."""
    
    def __init__(self, base_time: Optional[datetime] = None):
        """
        Initialize TimeController.
        
        Args:
            base_time: Starting time for controlled time. Defaults to 2024-01-01 00:00:00 UTC
        """
        self.base_time = base_time or datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        self.offset = timedelta()
        self._patchers: List[mock._patch] = []
        self._original_functions = {}
        self._started = False
    
    def start(self):
        """Start time control with monkey patching."""
        if self._started:
            logger.warning("TimeController already started")
            return
        
        # Store original functions
        self._original_functions = {
            'time.time': time.time,
            'time.monotonic': time.monotonic,
            'time.perf_counter': time.perf_counter,
            'datetime.now': datetime.now,
            'datetime.utcnow': datetime.utcnow,
        }
        
        # Patch time.time()
        self._patchers.append(
            mock.patch('time.time', side_effect=self._controlled_time)
        )
        
        # Patch time.monotonic() for timing measurements
        self._patchers.append(
            mock.patch('time.monotonic', side_effect=self._controlled_monotonic)
        )
        
        # Patch time.perf_counter() for performance measurements
        self._patchers.append(
            mock.patch('time.perf_counter', side_effect=self._controlled_perf_counter)
        )
        
        # Note: Patching datetime is more complex due to C implementation
        # For now, skip datetime patching to avoid errors
        # In production, use freezegun or similar library
        logger.debug("Datetime patching skipped - use freezegun for full datetime control")
        
        # Start all patchers
        for patcher in self._patchers:
            patcher.start()
        
        self._started = True
        logger.info(f"TimeController started with base time: {self.base_time}")
    
    def stop(self):
        """Stop time control and restore original functions."""
        if not self._started:
            return
        
        for patcher in self._patchers:
            try:
                patcher.stop()
            except Exception as e:
                logger.error(f"Error stopping patcher: {e}")
        
        self._patchers.clear()
        self._started = False
        logger.info("TimeController stopped")
    
    def advance(self, seconds: float = 0, minutes: float = 0, 
                hours: float = 0, days: float = 0):
        """
        Advance controlled time.
        
        Args:
            seconds: Number of seconds to advance
            minutes: Number of minutes to advance
            hours: Number of hours to advance
            days: Number of days to advance
        """
        delta = timedelta(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            days=days
        )
        self.offset += delta
        logger.debug(f"Time advanced by {delta}, new offset: {self.offset}")
    
    def set_time(self, target_time: datetime):
        """
        Set controlled time to a specific datetime.
        
        Args:
            target_time: Target datetime to set
        """
        if not target_time.tzinfo:
            target_time = target_time.replace(tzinfo=timezone.utc)
        
        self.offset = target_time - self.base_time
        logger.debug(f"Time set to {target_time}")
    
    def reset(self):
        """Reset time to base time."""
        self.offset = timedelta()
        logger.debug(f"Time reset to base: {self.base_time}")
    
    @property
    def current_time(self) -> datetime:
        """Get current controlled time as datetime."""
        return self.base_time + self.offset
    
    def _controlled_time(self) -> float:
        """Return controlled Unix timestamp."""
        return self.current_time.timestamp()
    
    def _controlled_monotonic(self) -> float:
        """Return controlled monotonic time."""
        # Use offset in seconds for monotonic time
        return self.offset.total_seconds()
    
    def _controlled_perf_counter(self) -> float:
        """Return controlled performance counter."""
        # Use high-precision offset for performance counter
        return self.offset.total_seconds()
    
    def _controlled_now(self, tz=None) -> datetime:
        """Return controlled datetime.now()."""
        current = self.current_time
        if tz:
            current = current.astimezone(tz)
        else:
            # Remove timezone info for naive datetime
            current = current.replace(tzinfo=None)
        return current
    
    def _controlled_utcnow(self) -> datetime:
        """Return controlled datetime.utcnow()."""
        # Return naive UTC datetime
        return self.current_time.replace(tzinfo=None)
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


class TimeControlledTest:
    """Mixin class for tests that need time control."""
    
    def setup_time_control(self, base_time: Optional[datetime] = None):
        """Set up time control for the test."""
        self.time_controller = TimeController(base_time)
        self.time_controller.start()
    
    def teardown_time_control(self):
        """Tear down time control after the test."""
        if hasattr(self, 'time_controller'):
            self.time_controller.stop()
    
    def advance_time(self, **kwargs):
        """Advance controlled time. See TimeController.advance for arguments."""
        if hasattr(self, 'time_controller'):
            self.time_controller.advance(**kwargs)
    
    def set_test_time(self, target_time: datetime):
        """Set controlled time to specific datetime."""
        if hasattr(self, 'time_controller'):
            self.time_controller.set_time(target_time)