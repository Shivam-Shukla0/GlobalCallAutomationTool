from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import SubmitField


class UploadQueueForm(FlaskForm):
    queue_file = FileField(
        "Queue CSV",
        validators=[FileRequired(), FileAllowed(["csv"], "CSV files only.")],
    )
    submit = SubmitField("Upload")
