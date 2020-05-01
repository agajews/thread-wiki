from bson import ObjectId


class Model:
    _fields = None

    def __init__(self, **kwargs):
        for name, field in self.fields().items():
            assert name in kwargs
            val = kwargs[name]
            assert field.check_type(val)
            setattr(self, name, val)

    @classmethod
    def fields(cls):
        if cls._fields is None:
            cls._fields = {}
            for key, val in cls.__dict__.items():
                if key[0] != "_":
                    if isinstance(val, Field):
                        cls._fields[key] = val
        return cls._fields

    @classmethod
    def from_dict(cls, data):
        vals = {}
        for name in self.fields():
            field = self.fields[name]
            if field.required:
                vals[name] = field.from_dict(self.fields[name])
            else:
                vals[name] = None
        return cls(**vals)

    def to_dict(self):
        vals = {}
        for name, field in self.fields().items():
            vals[name] = field.to_dict(getattr(self, name))
        return vals

    def copy(self):
        vals = {}
        for name, field in self.fields().items():
            vals[name] = field.copy(getattr(self, name))
        return self.__class__(**vals)

    def __eq__(self, other):
        return self.to_dict() == other.to_dict()


class Field:
    def __init__(self, model, required=True):
        assert issubclass(model, Model)
        self.model = model
        self.required = required

    def from_dict(self, data):
        if self.required:
            assert data is not None
        return self.model.from_dict(data)

    def to_dict(self, data):
        if self.required:
            assert data is not None
        if data is None:
            return None
        return data.to_dict()

    def copy(self, data):
        if self.required:
            assert data is not None
        if data is None:
            return None
        return data.copy()


class List:
    def __init__(self, model, required=True):
        assert issubclass(model, Model)
        self.model = model
        self.required = required

    def from_dict(self, data):
        if self.required:
            assert data is not None
        return [self.model.from_dict(elem) for elem in data]

    def to_dict(self, data):
        if self.required:
            assert data is not None
        if data is None:
            return None
        return [elem.to_dict() for elem in data]

    def copy(self, data):
        if self.required:
            assert data is not None
        if data is None:
            return None
        return [elem.copy() for elem in data]


class Literal(Model):
    def __init__(self, val):
        self.val = val

    @classmethod
    def from_dict(cls, val):
        assert isinstance(val, cls.type)
        return cls(val)

    def to_dict(self):
        return self.val

    def copy(self):
        return self.__class__(self.val)


class String(Literal):
    type = str


class Int(Literal):
    type = int


class Float(Literal):
    type = float


class Boolean(Literal):
    type = bool


class ObjectRef(Literal):
    type = ObjectId
