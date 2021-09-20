-- Drops all EAS tables and data.
-- When EAS_SERVICE_TYPE=SQL, EAS will recreate tables on the next startup

-- Legacy Tables
DROP TABLE IF EXISTS main.user_attribute_rel;
DROP TABLE IF EXISTS main.attributes;
DROP TABLE IF EXISTS main.users;
DROP TABLE IF EXISTS main.authorityNamespace;

-- Current Tables
DROP TABLE IF EXISTS main.attributeName;
DROP TABLE IF EXISTS main.attributeValue;
DROP TABLE IF EXISTS main.authorityNamespace;
DROP TABLE IF EXISTS main.entity;
DROP TABLE IF EXISTS main.entityAttribute;
DROP TABLE IF EXISTS main.ruleType;
DROP VIEW IF EXISTS main.attribute;
DROP VIEW IF EXISTS main.entityAttributeView;