class ParserFindTagException(Exception):
    """Вызывается, когда парсер не может найти тег."""


class PythonVersionsException(Exception):
    """Вызывается, когда парсер не смог найти список версий Python."""


class EmptyResponseException(Exception):
    """Вызывается, когда когда получен пустой ответ при загрузке страницы."""
