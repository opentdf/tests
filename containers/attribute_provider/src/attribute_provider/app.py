import connexion
import importlib_resources
import base64
import logging
import pprint
from flask import Flask
from flask import request
from flask import jsonify
from flask import current_app


def post_from_keycloak_protocol_mapper_impl(*args, **kwargs):
    current_app.logger.debug(pprint.pformat(request.args, indent=2))
    current_app.logger.debug(pprint.pformat(request.headers, indent=2))
    current_app.logger.debug(pprint.pformat(request.json, indent=2))

    merged_claims = {}
    # The "proof of possession" tdf claim - the minimal claimset that can be returned
    # is just this one property - if NO public key is recieved sufficient to populate this property,
    # then this service should ALWAYS return an empty response, which is equivalent to ACCESS DENIED.
    #
    # If a public key IS recieved sufficient to populate this property, than this is the minimum response
    # that the service should respond with in all cases.
    tdf_claims_minimal_attributes = {
        "client_public_signing_key": "",
        "tdf_spec_version": "4.0.0",
    }

    # This is an example claimset containing example subject and object attributes.
    # These attributes will be merged with the minimal claims object if a full
    # claimset response has been requested by the IdP (e.g. if the IdP is requesting a claims object for
    # its userinfo endpoint versus for its auth token endpoint)
    #
    # tl;dr sometimes IdPs want the WHOLE claims object from this service, and sometimes they don't.
    tdf_claims_full_attributes = {
        "subject_attributes": [
            {"attribute": "https://example.com/attr/Classification/value/S"},
            {"attribute": "https://example.com/attr/COI/value/PRX"},
        ]
    }

    # If no pubkey header recieved, then no error, but also no custom claims, rejected
    if "client_pk" not in request.json:
        pass
    else:
        # The POST data approach for passing the public key:
        clientKey = request.json["client_pk"]
        current_app.logger.debug("UNPARSED KEY: %s", clientKey)
        parsed_pk = parse_pk(clientKey)
        current_app.logger.debug("PARSED PK: %s", parsed_pk)
        tdf_claims_minimal_attributes["client_public_signing_key"] = parsed_pk

        current_app.logger.debug("Appending minimal (PoP) claims")
        merged_claims.update(tdf_claims_minimal_attributes)

        if (
            "claim_request_type" in request.json
            and request.json["claim_request_type"] == "full_claims"
        ):
            current_app.logger.debug("Appending full claims")
            merged_claims.update(tdf_claims_full_attributes)

    current_app.logger.debug(
        "responding with: %s" % (pprint.pformat(merged_claims, indent=2)),
    )
    response = jsonify(merged_claims)
    return response


def parse_pk(raw_pk):
    # Unfortunately, not all base64 implementations pad base64
    # strings in the way that Python expects (dependent on the length)
    # - fortunately, we can easily add the padding ourselves here if
    # it's needed.
    # See: https://gist.github.com/perrygeo/ee7c65bb1541ff6ac770
    clientKey = f"{raw_pk}{'=' * ((4 - len(raw_pk) % 4) % 4)}"
    return base64.b64decode(clientKey).decode("ascii")


def create_app(test_config=None):
    app = Flask(__name__)
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    app = connexion.FlaskApp(__name__)

    # Connexion will link REST endpoints to handlers using the openapi.yaml file
    openapi_file = importlib_resources.files(__package__) / "api" / "openapi.yaml"
    # FIXME:  do swagger ui options later
    app.add_api(openapi_file, strict_validation=True)

    @app.route("/", methods=["POST"])
    def post_from_keycloak_protocol_mapper(*args, **kwargs):
        return post_from_keycloak_protocol_mapper_impl(*args, **kwargs)

    # N.B.  in connexion, connexion_app.app is a Flask app, not "app".
    return app.app