from __future__ import annotations

from dataclasses import asdict
from typing import Any

from flask import Flask, current_app, g, jsonify, request
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.database import IrisConnectionFactory
from app.repositories import CandidateRepository, PropositionRepository

from .contracts import AskRequest, CandidateFilters, SearchRequest
from .services import ServiceFactory


def create_app(
    settings: Settings | None = None,
    connection_factory: Any | None = None,
    service_factory: Any | None = None,
) -> Flask:
    configured = settings or get_settings()
    application = Flask(__name__)
    application.config.update(
        SETTINGS=configured,
        CONNECTION_FACTORY=connection_factory or IrisConnectionFactory(configured),
        SERVICE_FACTORY=service_factory or ServiceFactory(configured),
        JSON_SORT_KEYS=False,
    )
    _register_lifecycle(application)
    _register_routes(application)
    _register_errors(application)
    return application


def _register_lifecycle(application: Flask) -> None:
    @application.before_request
    def open_connection() -> None:
        g.iris_connection = current_app.config["CONNECTION_FACTORY"].connect()

    @application.teardown_request
    def close_connection(_error: BaseException | None) -> None:
        connection = g.pop("iris_connection", None)
        if connection is not None:
            connection.close()


def _register_routes(application: Flask) -> None:
    @application.get("/health")
    def health() -> Any:
        cursor = g.iris_connection.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            cursor.close()
        return jsonify({"status": "ok"})

    @application.get("/candidates")
    def candidates() -> Any:
        filters = CandidateFilters.model_validate(request.args.to_dict())
        repository = _candidate_repository()
        values = repository.list(filters.name, filters.party, filters.state, filters.office)
        return jsonify({"items": [asdict(item) for item in values]})

    @application.get("/candidates/<int:candidate_id>")
    def candidate(candidate_id: int) -> Any:
        value = _candidate_repository().find_by_id(candidate_id)
        if value is None:
            raise LookupError("candidate not found")
        return jsonify(asdict(value))

    @application.get("/candidates/<int:candidate_id>/propositions")
    def propositions(candidate_id: int) -> Any:
        if _candidate_repository().find_by_id(candidate_id) is None:
            raise LookupError("candidate not found")
        repository = PropositionRepository(g.iris_connection, _settings().iris_sql_schema)
        return jsonify({"items": repository.list_by_candidate(candidate_id)})

    @application.post("/search")
    def search() -> Any:
        payload = SearchRequest.model_validate(request.get_json(silent=True) or {})
        retrieval = current_app.config["SERVICE_FACTORY"].search(g.iris_connection)
        results = retrieval.search(
            payload.query,
            candidate_id=payload.candidate_id,
            source_type=payload.source_type,
            top_k=payload.top_k,
        )
        return jsonify({"results": [asdict(item) for item in results]})

    @application.post("/ask")
    def ask() -> Any:
        payload = AskRequest.model_validate(request.get_json(silent=True) or {})
        service = current_app.config["SERVICE_FACTORY"].rag(g.iris_connection)
        return jsonify(service.ask(payload.question, payload.candidate_id).as_dict())


def _register_errors(application: Flask) -> None:
    @application.errorhandler(ValidationError)
    def invalid_request(error: ValidationError) -> tuple[Any, int]:
        details = error.errors(include_url=False, include_context=False)
        return jsonify({"error": "invalid_request", "details": details}), 400

    @application.errorhandler(LookupError)
    def not_found(error: LookupError) -> tuple[Any, int]:
        return jsonify({"error": "not_found", "message": str(error)}), 404

    @application.errorhandler(ValueError)
    def invalid_value(error: ValueError) -> tuple[Any, int]:
        return jsonify({"error": "invalid_request", "message": str(error)}), 400


def _settings() -> Settings:
    return current_app.config["SETTINGS"]


def _candidate_repository() -> CandidateRepository:
    return CandidateRepository(g.iris_connection, _settings().iris_sql_schema)
