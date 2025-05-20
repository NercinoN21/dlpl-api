from bcrypt import gensalt, hashpw
from pydantic import BaseModel, Field, field_validator, model_validator
from pyotp import random_base32
from datetime import datetime, timedelta
from typing import Optional
import re
from src.utils import adjust_cpf


def validate_semester_format(semester: str) -> str:
    """Validate semester format (XXXX.X)."""
    try:
        year, semester_num = semester.split('.')
    except ValueError:
        raise ValueError('O formato do semestre deve ser XXXX.X (exemplo: 2024.1)')
    
    if not year.isdigit() or len(year) != 4:
        raise ValueError('O ano deve conter exatamente 4 dígitos')
    
    if year.startswith('0'):
        raise ValueError('O ano não pode começar com zero')
    
    if not semester_num.isdigit() or len(semester_num) != 1 or semester_num == '0':
        raise ValueError('O semestre deve ser um único dígito de 1 a 9')
    
    return semester


class UserRegistrationFormData(BaseModel):
    name: str
    password: str
    model_config = {'extra': 'forbid'}

    def __init__(self, **data):
        super().__init__(**data)
        self.password = hashpw(
            str.encode(data.get('password')), gensalt()
        ).decode('utf-8')
        self._otp_secret = random_base32()


class UserLoginFormData(BaseModel):
    name: str
    password: str
    model_config = {'extra': 'forbid'}


class UserUpdateFormData(BaseModel):
    name: str
    new_name: str = Field(None)
    new_password: str = Field(None)
    model_config = {'extra': 'forbid'}

    def __init__(self, **data):
        super().__init__(**data)
        self.new_password = hashpw(
            str.encode(data.get('new_password')), gensalt()
        ).decode('utf-8')


class UserUpdateAdminFormData(BaseModel):
    name: str
    admin: bool
    model_config = {'extra': 'forbid'}

class UserUpdateActiveFormData(BaseModel):
    name: str
    is_active: bool
    model_config = {'extra': 'forbid'}


class TurmaCreateFormData(BaseModel):
    name: str
    semester: str
    model_config = {'extra': 'forbid'}

    @field_validator('semester')
    @classmethod
    def validate_semester(cls, v: str) -> str:
        return validate_semester_format(v)


class TurmaUpdateFormData(BaseModel):
    name: str
    semester: str
    new_name: str = None
    new_semester: str = None
    model_config = {'extra': 'forbid'}

    @field_validator('semester', 'new_semester')
    @classmethod
    def validate_semester(cls, v: str) -> str:
        return validate_semester_format(v)


class TurmaDeleteFormData(BaseModel):
    name: str
    semester: str
    model_config = {'extra': 'forbid'}

    @field_validator('semester')
    @classmethod
    def validate_semester(cls, v: str) -> str:
        return validate_semester_format(v)


class ResultCreateFormData(BaseModel):
    ano_sisu: int
    nome_turma: str
    semestre: str
    nome_aluno: str
    curso_aluno: str
    nota_suficiencia: float
    escolha: str
    model_config = {'extra': 'forbid'}


class ResultUpdateFormData(BaseModel):
    nome_turma: str = Field(None)
    semestre: str = Field(None)
    escolha: str = Field(None)
    model_config = {'extra': 'forbid'}


class ConfigCreateUpdateFormData(BaseModel):
    activeSemester: str
    enrollmentStartDate: datetime
    enrollmentEndDate: datetime
    model_config = {'extra': 'forbid'}

    @field_validator('activeSemester')
    @classmethod
    def validate_active_semester(cls, v: str) -> str:
        return validate_semester_format(v)


class EnrollmentCreateFormData(BaseModel):
    name: str
    cpf: str
    course: str
    choice: str
    turma: str
    semester: str

    @field_validator('cpf')
    def validate_cpf(cls, v):
        try:
            return adjust_cpf(v)
        except Exception as e:
            raise ValueError(str(e))

    @field_validator('semester')
    def validate_semester(cls, v):
        return validate_semester_format(v)


class EnrollmentUpdateFormData(BaseModel):
    name: str
    cpf: str
    course: str
    semester: str
    new_semestre: Optional[str] = None
    new_turma: Optional[str] = None
    new_choice: Optional[str] = None

    @field_validator('cpf')
    def validate_cpf(cls, v):
        try:
            return adjust_cpf(v)
        except Exception as e:
            raise ValueError(str(e))

    @field_validator('semester', 'new_semestre')
    def validate_semester(cls, v):
        if v and not re.match(r'^\d{4}\.\d$', v):
            raise ValueError('Invalid semester format. Use YYYY.P format (e.g., 2024.1)')
        return v


class EnrollmentDeleteFormData(BaseModel):
    name: str
    cpf: str
    course: str
    semester: str

    @field_validator('cpf')
    def validate_cpf(cls, v):
        try:
            return adjust_cpf(v)
        except Exception as e:
            raise ValueError(str(e))

    @field_validator('semester')
    def validate_semester(cls, v):
        if not re.match(r'^\d{4}\.\d$', v):
            raise ValueError('Invalid semester format. Use YYYY.P format (e.g., 2024.1)')
        return v
