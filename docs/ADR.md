# Architecture Decision Records

## 001: FastAPI + Next.js Monorepo

FastAPI gives a typed, inspectable API surface with automatic OpenAPI docs. Next.js gives a production-ready React UI, server rendering, and straightforward deployment.

## 002: PostgreSQL as Source of Truth

Customer, order, campaign, event, setting, prompt, and audit data are relational with strong tenant boundaries. PostgreSQL also supports JSONB for configurable rules and prompt metadata.

## 003: SQL-Safe Segment Compiler

Natural-language segmentation is compiled through a whitelist-based intermediate representation rather than free-form SQL. This allows dynamic marketer intent without exposing arbitrary query execution.

## 004: Simulator as Separate Microservice

Messaging providers behave asynchronously and unreliably. The simulator models delivery, open/read, click, conversion, failure, retries, and dead letters so the CRM can be evaluated without external vendor accounts.
