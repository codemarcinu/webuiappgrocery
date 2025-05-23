from datetime import datetime
from typing import Optional
from wtforms import Form, StringField, FloatField, IntegerField, SelectField, DateField, FileField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional as OptionalValidator, ValidationError
from models import KategoriaProduktu

class DodajParagonForm(Form):
    file = FileField('Plik paragonu', validators=[
        DataRequired(message='Wybierz plik paragonu')
    ])
    komentarz = TextAreaField('Komentarz', validators=[
        OptionalValidator(),
        Length(max=500, message='Komentarz nie może być dłuższy niż 500 znaków')
    ])

class EdytujProduktForm(Form):
    nazwa = StringField('Nazwa produktu', validators=[
        DataRequired(message='Nazwa produktu jest wymagana'),
        Length(min=1, max=100, message='Nazwa produktu musi mieć od 1 do 100 znaków')
    ])
    kategoria = SelectField('Kategoria', choices=[(k.value, k.value) for k in KategoriaProduktu], validators=[
        DataRequired(message='Wybierz kategorię produktu')
    ])
    cena = FloatField('Cena', validators=[
        DataRequired(message='Cena jest wymagana'),
        NumberRange(min=0.01, message='Cena musi być większa niż 0')
    ])
    ilosc_na_paragonie = IntegerField('Ilość na paragonie', validators=[
        DataRequired(message='Ilość jest wymagana'),
        NumberRange(min=1, message='Ilość musi być większa niż 0')
    ])
    data_waznosci = DateField('Data ważności', format='%Y-%m-%d', validators=[
        OptionalValidator()
    ])

    def validate_data_waznosci(self, field):
        if field.data and field.data < datetime.now().date():
            raise ValidationError('Data ważności nie może być z przeszłości') 