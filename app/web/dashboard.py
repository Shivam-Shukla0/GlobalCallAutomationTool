"""Dashboard + queue control. Every route requires login."""
import logging
import os

from flask import (
    Blueprint, current_app, flash, redirect, render_template, url_for,
)
from flask_login import login_required
from werkzeug.utils import secure_filename

from ..extensions import limiter
from ..services import queue_service
from ..services.stats import queue_statistics, recent_calls
from .forms import UploadQueueForm

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    return render_template(
        "dashboard.html",
        stats=queue_statistics(),
        recent_calls=recent_calls(10),
        upload_form=UploadQueueForm(),
    )


@dashboard_bp.route("/upload-queue", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def upload_queue():
    form = UploadQueueForm()
    if not form.validate_on_submit():
        flash("Please choose a valid CSV file.", "error")
        return redirect(url_for("dashboard.index"))

    file = form.queue_file.data
    filename = secure_filename(file.filename)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    file.save(path)
    try:
        count = queue_service.load_from_csv(path)
        flash(f"Loaded {count} valid numbers into the queue.", "success")
    except Exception as exc:  # noqa: BLE001
        logger.error("Queue upload failed: %s", exc)
        flash("Failed to parse the uploaded file.", "error")
    return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/start-automation", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def start_automation():
    from ..tasks.call_tasks import drain_queue  # lazy import avoids circular load
    drain_queue.delay()
    flash("Dialing started in the background.", "success")
    return redirect(url_for("dashboard.index"))
