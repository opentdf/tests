"""Randomness control utilities for deterministic testing."""

import random
import hashlib
import secrets
from typing import Dict, Optional, Any, List
from unittest import mock
import logging

# NumPy is optional
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

logger = logging.getLogger(__name__)


class DeterministicRandom:
    """Deterministic random generator for testing."""
    
    def __init__(self, seed: int):
        self.seed = seed
        self._generator = random.Random(seed)
    
    def random(self) -> float:
        """Generate random float in [0.0, 1.0)."""
        return self._generator.random()
    
    def randint(self, a: int, b: int) -> int:
        """Generate random integer in range [a, b]."""
        return self._generator.randint(a, b)
    
    def choice(self, seq):
        """Choose random element from sequence."""
        return self._generator.choice(seq)
    
    def choices(self, population, weights=None, k=1):
        """Choose k elements with replacement."""
        return self._generator.choices(population, weights=weights, k=k)
    
    def sample(self, population, k):
        """Choose k unique elements."""
        return self._generator.sample(population, k)
    
    def shuffle(self, seq):
        """Shuffle sequence in-place."""
        self._generator.shuffle(seq)
    
    def randbytes(self, n: int) -> bytes:
        """Generate n random bytes."""
        # Use deterministic byte generation
        result = bytearray()
        for _ in range(n):
            result.append(self._generator.randint(0, 255))
        return bytes(result)
    
    def uniform(self, a: float, b: float) -> float:
        """Generate random float in range [a, b]."""
        return self._generator.uniform(a, b)
    
    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        """Generate random number from Gaussian distribution."""
        return self._generator.gauss(mu, sigma)


class DeterministicCrypto:
    """Deterministic crypto-like randomness for testing."""
    
    def __init__(self, seed: int):
        self.seed = seed
        self._counter = 0
    
    def randbytes(self, n: int) -> bytes:
        """Generate deterministic 'secure' random bytes."""
        # Use SHA256 for deterministic but unpredictable bytes
        data = f"{self.seed}:{self._counter}:{n}".encode()
        self._counter += 1
        
        result = bytearray()
        block_num = 0
        
        while len(result) < n:
            block_data = data + block_num.to_bytes(4, 'big')
            hash_bytes = hashlib.sha256(block_data).digest()
            result.extend(hash_bytes)
            block_num += 1
        
        return bytes(result[:n])
    
    def token_bytes(self, nbytes: Optional[int] = None) -> bytes:
        """Generate deterministic token bytes."""
        if nbytes is None:
            nbytes = 32
        return self.randbytes(nbytes)
    
    def token_hex(self, nbytes: Optional[int] = None) -> str:
        """Generate deterministic token as hex string."""
        return self.token_bytes(nbytes).hex()
    
    def token_urlsafe(self, nbytes: Optional[int] = None) -> str:
        """Generate deterministic URL-safe token."""
        import base64
        tok = self.token_bytes(nbytes)
        return base64.urlsafe_b64encode(tok).rstrip(b'=').decode('ascii')
    
    def choice(self, seq):
        """Deterministically choose from sequence."""
        if not seq:
            raise IndexError("Cannot choose from empty sequence")
        # Use hash of counter to select index
        index_bytes = hashlib.sha256(f"{self.seed}:choice:{self._counter}".encode()).digest()
        self._counter += 1
        index = int.from_bytes(index_bytes[:4], 'big') % len(seq)
        return seq[index]


class RandomnessController:
    """Control randomness for deterministic testing."""
    
    def __init__(self, seed: int = 42):
        """
        Initialize RandomnessController.
        
        Args:
            seed: Base seed for all random generators
        """
        self.seed = seed
        self.generators: Dict[str, Any] = {}
        self._patchers: List[mock._patch] = []
        self._started = False
        self._original_functions = {}
    
    def start(self):
        """Initialize all random number generators with deterministic seeds."""
        if self._started:
            logger.warning("RandomnessController already started")
            return
        
        # Store original functions
        self._original_functions = {
            'random': random,
            'secrets': secrets,
        }
        
        # Python's built-in random
        random.seed(self.seed)
        
        # NumPy random if available
        if HAS_NUMPY:
            np.random.seed(self.seed)
            self.generators['numpy'] = np.random.RandomState(self.seed)
        else:
            logger.debug("NumPy not available, skipping numpy random seeding")
        
        # Create deterministic generators
        self.generators['default'] = DeterministicRandom(self.seed)
        self.generators['crypto'] = DeterministicCrypto(self.seed)
        
        # Patch secrets module for deterministic "secure" randomness
        self._patch_secrets()
        
        self._started = True
        logger.info(f"RandomnessController started with seed: {self.seed}")
    
    def stop(self):
        """Stop randomness control and restore original functions."""
        if not self._started:
            return
        
        for patcher in self._patchers:
            try:
                patcher.stop()
            except Exception as e:
                logger.error(f"Error stopping patcher: {e}")
        
        self._patchers.clear()
        self._started = False
        logger.info("RandomnessController stopped")
    
    def _patch_secrets(self):
        """Patch secrets module to use deterministic crypto."""
        crypto = self.generators['crypto']
        
        # Patch secrets.randbits
        self._patchers.append(
            mock.patch('secrets.randbits', side_effect=lambda k: int.from_bytes(
                crypto.randbytes((k + 7) // 8), 'big') >> (8 - k % 8) if k % 8 else int.from_bytes(
                crypto.randbytes(k // 8), 'big'))
        )
        
        # Patch secrets.token_bytes
        self._patchers.append(
            mock.patch('secrets.token_bytes', side_effect=crypto.token_bytes)
        )
        
        # Patch secrets.token_hex
        self._patchers.append(
            mock.patch('secrets.token_hex', side_effect=crypto.token_hex)
        )
        
        # Patch secrets.token_urlsafe
        self._patchers.append(
            mock.patch('secrets.token_urlsafe', side_effect=crypto.token_urlsafe)
        )
        
        # Patch secrets.choice
        self._patchers.append(
            mock.patch('secrets.choice', side_effect=crypto.choice)
        )
        
        # Start all patchers
        for patcher in self._patchers:
            patcher.start()
    
    def get_generator(self, name: str = 'default') -> DeterministicRandom:
        """
        Get a named random generator.
        
        Args:
            name: Name of the generator
        
        Returns:
            DeterministicRandom generator
        """
        if name not in self.generators:
            # Create new generator with derived seed
            derived_seed = self.seed + hash(name) % (2**31)
            self.generators[name] = DeterministicRandom(derived_seed)
            logger.debug(f"Created new generator '{name}' with seed {derived_seed}")
        
        return self.generators[name]
    
    def reset_generator(self, name: str = 'default'):
        """Reset a named generator to its initial state."""
        if name in self.generators:
            if isinstance(self.generators[name], DeterministicRandom):
                derived_seed = self.seed + hash(name) % (2**31) if name != 'default' else self.seed
                self.generators[name] = DeterministicRandom(derived_seed)
            elif name == 'crypto':
                self.generators[name] = DeterministicCrypto(self.seed)
            logger.debug(f"Reset generator '{name}'")
    
    def set_numpy_seed(self, seed: Optional[int] = None):
        """Set NumPy random seed."""
        seed = seed or self.seed
        if HAS_NUMPY:
            np.random.seed(seed)
            self.generators['numpy'] = np.random.RandomState(seed)
            logger.debug(f"Set NumPy seed to {seed}")
        else:
            logger.debug("NumPy not available")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


class RandomnessControlledTest:
    """Mixin class for tests that need randomness control."""
    
    def setup_randomness_control(self, seed: int = 42):
        """Set up randomness control for the test."""
        self.randomness_controller = RandomnessController(seed)
        self.randomness_controller.start()
    
    def teardown_randomness_control(self):
        """Tear down randomness control after the test."""
        if hasattr(self, 'randomness_controller'):
            self.randomness_controller.stop()
    
    def get_test_random(self, name: str = 'default') -> DeterministicRandom:
        """Get a deterministic random generator for the test."""
        if hasattr(self, 'randomness_controller'):
            return self.randomness_controller.get_generator(name)
        raise RuntimeError("Randomness control not set up")