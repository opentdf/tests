"""The web module implements the exposed network interface.

The web layer may also support message queues and other external
interface technologies. Currently only a HTTP framework (Flask) is provided.

The code in this folder is intended to insulate the business logic from any
knowledge of how the external connections are made. If changes in the external
connections are required they will be made in this, and only this, directory
by design. Major changes such as moving from HTTP calls to websockets or
message queues should have no impact on any code external to this directory.

Web interface modules should validate all external inputs. Usually this is
done with a tdf3_kas_core.schema.
"""

from .create_context import create_context  # noqa: F401
from .heartbeat import ping
from .public_key import get
from .rewrap import rewrap
from .upsert import upsert
from .run_service_with_exceptions import run_service_with_exceptions
