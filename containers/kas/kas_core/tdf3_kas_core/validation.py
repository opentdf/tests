"""Attribute validation regex."""

import re


SCHEME_PATTERN = r"""(
    https?                           # starts with a http or https scheme
    :\/\/                            # followed by colon slash slash
)"""

HOST_PATTERN = r"""(
    (
        (                            #    Pattern 1 - "localhost:4000"
            [a-z0-9]                 # 2+ char word; starts with a letter
            [a-z0-9]{1,}             # followed by one or more alphanumerics
            :                        # then a hyphen
            [0-9]{1,4}               # followed by a 1-4 digit port no.
        )
    )|(                              #   Pattern 2 - "www.example.com"
        (?:www\.|(?!www))            # starts with www. (or not www)
        (                            # then words that
            [a-z0-9]                 # start with an alphanumeric
            [a-z0-9-]*               # have zero or more alphanumerics or '-'
            [a-z0-9]                 # and end with an alphanumeric
            \.                       # followed by a dot
        )+                           # there can be one or more of these words
        [^\s]{2,}                    # terminated with a 2-string or longer
    )|(
        (                            #    Pattern 1 - "127.0.0.1:4000"
            [0-9]{1,3}\.             # one to three digits and a dot
            [0-9]{1,3}\.             # one to three digits and a dot
            [0-9]{1,3}\.             # one to three digits and a dot
            [0-9]{1,3}               # one to three digits (basic, not 0-255)
            :                        # then a hyphen
            [0-9]{1,4}               # followed by a 1-4 digit port no.
        )
    )
)"""


NAME_PATTERN = r"""(
    \/attr\/                         # First /attr/
    [a-z0-9]([a-z0-9-]+[a-z0-9])?    # then the attribute policy name
)"""

VALUE_PATTERN = r"""(
    \/value\/                        # First /value/
    [a-z0-9]([a-z0-9-]+[a-z0-9])?    # then the attribute value name
)"""

ATTR_AUTHORITY_PATTERN = SCHEME_PATTERN + HOST_PATTERN
ATTR_NAMESPACE_PATTERN = ATTR_AUTHORITY_PATTERN + NAME_PATTERN
ATTR_ATTRIBUTE_PATTERN = ATTR_NAMESPACE_PATTERN + VALUE_PATTERN

flags = re.IGNORECASE | re.VERBOSE

# These checkers are the main export
attr_authority_check = re.compile(ATTR_AUTHORITY_PATTERN, flags)
attr_namespace_check = re.compile(ATTR_NAMESPACE_PATTERN, flags)
attr_attribute_check = re.compile(ATTR_ATTRIBUTE_PATTERN, flags)
