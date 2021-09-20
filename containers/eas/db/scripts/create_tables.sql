-- In SQLite foreign keys need be enabled before use

PRAGMA foreign_keys = ON;
-- # Public Keys: entityObject calls them publicKey,
-- # attribute calls them pubKey, and the python also calls them pub_key and public_key

CREATE TABLE IF NOT EXISTS main.ruleType
(
    rule VARCHAR PRIMARY KEY
);

INSERT INTO ruleType (rule)
    VALUES ('anyOf'), ('allOf'), ('hierarchy')
EXCEPT
    SELECT rule FROM ruleType;

CREATE TABLE IF NOT EXISTS main.authorityNamespace
(
    namespace VARCHAR PRIMARY KEY COLLATE NOCASE,
    displayName VARCHAR,
    isDefault INTEGER
);

CREATE TABLE IF NOT EXISTS main.attributeName
(
    name VARCHAR,
    namespace VARCHAR COLLATE NOCASE,
    "order" VARCHAR,
    state INT,
    rule VARCHAR,
    PRIMARY KEY (name, namespace),
    FOREIGN KEY (namespace)
        REFERENCES authorityNamespace (namespace),
    FOREIGN KEY (rule)
        REFERENCES ruleType (rule)
);

CREATE TABLE IF NOT EXISTS main.attributeValue
(
    name VARCHAR NOT NULL,
    namespace VARCHAR NOT NULL COLLATE NOCASE,
    value VARCHAR NOT NULL,
    displayName VARCHAR,
    kasUrl VARCHAR,
    pubKey TEXT,
    isDefault INTEGER,
    state INT,
    PRIMARY KEY(namespace, name, value),
    FOREIGN KEY (namespace)
        REFERENCES authorityNamespace (namespace),
    FOREIGN KEY (namespace, name)
        REFERENCES attributeName (namespace,name)
);

CREATE TABLE IF NOT EXISTS main.entity
(
    userId VARCHAR
        primary key
        unique,
    name VARCHAR,
    email VARCHAR
        unique,
    nonPersonEntity INTEGER,
    state INT,
    pubKey TEXT
);

CREATE TABLE IF NOT EXISTS main.entityAttribute
(
    pk INTEGER not null
        constraint entity_attribute_pk
            primary key autoincrement,
    state int not null,
    userId VARCHAR NOT NULL,
    namespace VARCHAR NOT NULL COLLATE NOCASE,
    name VARCHAR NOT NULL,
    value VARCHAR NOT NULL,
    FOREIGN KEY (userId)
        REFERENCES entity (userId),
--     Design decision: separate namespace/name/value or use URI?
    FOREIGN KEY (namespace, name, value)
        REFERENCES attributeValue (namespace, name, value)
);

CREATE VIEW IF NOT EXISTS main.attribute
AS
    SELECT
        namespace || '/attr/' || name || '/value/' || value AS url,
        displayName,
        kasUrl,
        pubKey,
        isDefault,
        state,
        namespace,
        name,
        value
    FROM attributeValue;

CREATE VIEW IF NOT EXISTS main.entityAttributeView
AS
    SELECT
        e.userId,
        e.email,
        e.name,
        e.nonPersonEntity,
        e.state as entityState,
        a.state as attrState,
        e.pubKey,
        a.namespace || '/attr/' || a.name || '/value/' || a.value AS attribute_uri
    FROM entity as e
    LEFT JOIN entityAttribute as a
        ON e.userId = a.userId;

CREATE INDEX IF NOT EXISTS entity_attribute_attribute_keys_index
    ON entityAttribute (namespace, name, value);

CREATE INDEX IF NOT EXISTS entity_attribute_entity_id_index
    ON entityAttribute (userId);

CREATE UNIQUE INDEX IF NOT EXISTS entity_attribute_pk_uindex
    ON entityAttribute (pk);