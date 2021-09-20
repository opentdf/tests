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


ATTRIB_PATTERN = r"""(
    \/attr\/                         # First /attr/
    \w+                              # then the attribute policy name
)"""

VALUE_PATTERN = r"""(
    \/value\/                        # First /value/
    \w+                              # then the attribute value name
)"""

URL_PATTERN = SCHEME_PATTERN + HOST_PATTERN
ATTR_URL_PATTERN = URL_PATTERN + ATTRIB_PATTERN
ATTR_DESC_PATTERN = ATTR_URL_PATTERN + VALUE_PATTERN

flags = re.IGNORECASE | re.VERBOSE

# These checkers are the main export
url_check = re.compile(URL_PATTERN, flags)
attr_url_check = re.compile(ATTR_URL_PATTERN, flags)
attr_desc_check = re.compile(ATTR_DESC_PATTERN, flags)
