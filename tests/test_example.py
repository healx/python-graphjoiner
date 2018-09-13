from __future__ import unicode_literals

from hamcrest import assert_that

from .matchers import is_successful_result


def test_example():
    from sqlalchemy import Column, Integer, Unicode, ForeignKey
    from sqlalchemy.ext.declarative import declarative_base

    Base = declarative_base()

    class Author(Base):
        __tablename__ = "author"

        id = Column(Integer, primary_key=True)
        name = Column(Unicode, nullable=False)

    class Book(Base):
        __tablename__ = "book"

        id = Column(Integer, primary_key=True)
        title = Column(Unicode, nullable=False)
        genre = Column(Unicode, nullable=False)
        author_id = Column(Integer, ForeignKey(Author.id))




    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Author(name="PG Wodehouse"))
    session.add(Author(name="Joseph Heller"))
    session.add(Author(name="Jules Verne"))
    session.add(Book(title="Leave It to Psmith", author_id=1, genre="comedy"))
    session.add(Book(title="Right Ho, Jeeves", author_id=1, genre="comedy"))
    session.add(Book(title="Catch-22", author_id=2, genre="comedy"))
    session.add(Book(title="Around the World in Eighty Days", author_id=3, genre="adventure"))





    from graphql import GraphQLInt, GraphQLString, GraphQLArgument
    from graphjoiner import JoinType, RootJoinType, single, many, field
    from sqlalchemy.orm import Query

    def create_root():
        def fields():
            return {
                "books": many(
                    book_join_type,
                    books_query,
                    args={"genre": GraphQLArgument(type=GraphQLString)}
                )
            }

        def books_query(args, _, context):
            query = Query([]).select_from(Book)

            if "genre" in args:
                query = query.filter(Book.genre == args["genre"])

            return query

        return RootJoinType(name="Root", fields=fields)

    root = create_root()

    def fetch_immediates_from_database(selections, query, context):
        query = query.with_entities(*(
            selection.field.column_name
            for selection in selections
        ))

        return query.with_session(context.session).all()

    def create_book_join_type():
        def fields():
            return {
                "id": field(column_name="id", type=GraphQLInt),
                "title": field(column_name="title", type=GraphQLString),
                "genre": field(column_name="genre", type=GraphQLString),
                "authorId": field(column_name="author_id", type=GraphQLInt),
                "author": single(author_join_type, author_query, join={"authorId": "id"}),
            }

        def author_query(args, book_query, context):
            books = book_query.with_entities(Book.author_id).distinct().subquery()
            return Query([]) \
                .select_from(Author) \
                .join(books, books.c.author_id == Author.id)

        return JoinType(
            name="Book",
            fields=fields,
            fetch_immediates=fetch_immediates_from_database,
        )

    book_join_type = create_book_join_type()

    def create_author_join_type():
        def fields():
            return {
                "id": field(column_name="id", type=GraphQLInt),
                "name": field(column_name="name", type=GraphQLString),
            }

        return JoinType(
            name="Author",
            fields=fields,
            fetch_immediates=fetch_immediates_from_database,
        )
    author_join_type = create_author_join_type()


    from graphjoiner import execute

    query = """
        {
            books(genre: "comedy") {
                title
                author {
                    name
                }
            }
        }
    """

    class Context(object):
        def __init__(self, session):
            self.session = session

    result = execute(root, query, context=Context(session))

    assert_that(result, is_successful_result(data={
        "books": [
            {
                "title": "Leave It to Psmith",
                "author": {
                    "name": "PG Wodehouse"
                }
            },
            {
                "title": "Right Ho, Jeeves",
                "author": {
                    "name": "PG Wodehouse"
                }
            },
            {
                "title": "Catch-22",
                "author": {
                    "name": "Joseph Heller"
                }
            },
        ]
    }))

