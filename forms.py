# formularios con wtf

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from bdate import User

class RegisterForm(FlaskForm):
    username = StringField("Nombre de usuario", validators=[
        DataRequired(), 
        Length(min=4, max=25, message="El usuario debe tener entre 4 y 25 caracteres")
    ])
    
    password = PasswordField("Contraseña", validators=[
        DataRequired(), 
        Length(min=6, max=40, message="La contraseña debe tener entre 6 y 40 caracteres")
    ])
    
    confirm_password = PasswordField("Repetir Contraseña", validators=[
        DataRequired(), 
        EqualTo('password', message="Las contraseñas deben coincidir")
    ])
    
    submit = SubmitField("Registrar")

    # Validación personalizada para chequear si el usuario ya existe
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Ese nombre de usuario ya está en uso. Por favor elige otro.')

class LoginForm(FlaskForm):
    username = StringField("Usuario", validators=[DataRequired()])
    password = PasswordField("Contraseña", validators=[DataRequired()])
    remember = BooleanField("Recordarme")
    submit = SubmitField("Ingresar")