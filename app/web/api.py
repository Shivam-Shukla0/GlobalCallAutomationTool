"""JSON API for the dashboard front-end."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from ..extensions import limiter
from ..services.stats import queue_statistics, recent_calls

api_bp = Blueprint("api", __name__)


@api_bp.route("/queue-status")
@login_required
@limiter.limit("60 per minute")
def queue_status():
    return jsonify(queue_statistics())


@api_bp.route("/recent-calls")
@login_required
@limiter.limit("60 per minute")
def api_recent_calls():
    limit = request.args.get("limit", 20, type=int)
    return jsonify(recent_calls(limit))
