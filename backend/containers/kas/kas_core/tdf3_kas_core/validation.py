"""Attribute validation regex."""

import re


SCHEME_PATTERN = r"""(?:
    (?P<scheme>https?)               # starts with a http or https scheme
    :\/\/                            # followed by colon slash slash
)"""

HOST_PATTERN = r"""(?P<host>
    (?P<name>
        (?:                          #    Pattern 1 - localhost
            localhost                
        )|(?:                        #    Pattern 2 - standard names
            (?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)*(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,})\.?
        )|(?:                        #    IP v4 "127.0.0.1"
            [0-9]{1,3}\.
            [0-9]{1,3}\.
            [0-9]{1,3}\.
            [0-9]{1,3}
        )
    )
    (?:                              # Optional port
        :
        (?P<port>[0-9]{1,5})
    )?
    (?P<path>                        # Optional path
        \/
        [/.a-zA-Z0-9-]*
    )?
)"""


NAME_PATTERN = r"""(?:
    \/attr\/
    (?P<namespace>
        [a-z0-9]([a-z0-9-]+[a-z0-9])?
    )
)"""

VALUE_PATTERN = r"""(?:
    \/value\/
    (?P<value>
        [a-z0-9][a-z0-9-]*[a-z0-9]?
    )
)"""

ATTR_AUTHORITY_PATTERN = SCHEME_PATTERN + HOST_PATTERN
ATTR_NAMESPACE_PATTERN = ATTR_AUTHORITY_PATTERN + NAME_PATTERN
ATTR_ATTRIBUTE_PATTERN = ATTR_NAMESPACE_PATTERN + VALUE_PATTERN

flags = re.IGNORECASE | re.VERBOSE

# These checkers are the main export
attr_authority_check = re.compile(ATTR_AUTHORITY_PATTERN + "$", flags)
attr_namespace_check = re.compile(ATTR_NAMESPACE_PATTERN + "$", flags)
attr_attribute_check = re.compile(ATTR_ATTRIBUTE_PATTERN + "$", flags)
