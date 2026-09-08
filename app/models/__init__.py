"""
ORM 模型统一导出
"""
from app.models.film_source import FilmSource
from app.models.movie import MovieDetail
from app.models.search import SearchInfo
from app.models.slave_movie import SlaveMovieInfo

__all__ = ["FilmSource", "MovieDetail", "SlaveMovieInfo", "SearchInfo"]
