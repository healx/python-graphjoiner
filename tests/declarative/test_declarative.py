import attr
from graphql import GraphQLField, GraphQLInterfaceType, GraphQLNonNull, GraphQLString
from hamcrest import all_of, assert_that, contains, contains_inanyorder, equal_to, has_properties, has_string, instance_of, starts_with
import pytest

from graphjoiner.declarative import (
    Boolean,
    define_field,
    executor,
    extract,
    field,
    fields,
    field_set,
    first_or_null,
    InputObjectType,
    Int,
    join as _join,
    join_builder,
    single,
    single_or_null,
    List,
    many,
    RootType,
    NonNull,
    ObjectType,
    Selection,
    InterfaceType,
    select,
    String,
    undefined,
    _snake_case_to_camel_case,
)
from graphjoiner.schemas import parse_schema
from ..matchers import is_invalid_result, is_successful_result


class StaticDataObjectType(ObjectType):
    @staticmethod
    @join_builder
    def select(local, target, join=None):
        return _join.build(
            local,
            target,
            query=lambda parent_select: target.__records__,
            join_fields=join,
        )

    @classmethod
    def __fetch_immediates__(cls, selections, records, context):
        return [
            tuple(
                getattr(record, selection.field.attr_name)
                for selection in selections
            )
            for record in records
        ]

class TestRelationships(object):
    def test_single_relationship_raises_error_if_there_are_no_matching_results(self):
        class Root(RootType):
            author = single(lambda: self._join_to_authors(count=0))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_invalid_result(errors=contains_inanyorder(
            has_string("Expected 1 value but got 0"),
        )))


    def test_single_relationship_is_resolved_to_object_if_there_is_exactly_one_matching_result(self):
        class Root(RootType):
            author = single(lambda: self._join_to_authors(count=1))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_successful_result(data={
            "author": {"name": "PG Wodehouse"},
        }))


    def test_single_relationship_raises_error_if_there_are_multiple_matching_results(self):
        class Root(RootType):
            author = single(lambda: self._join_to_authors(count=2))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_invalid_result(errors=contains_inanyorder(
            has_string("Expected 1 value but got 2"),
        )))


    def test_single_or_null_relationship_is_resolved_to_null_if_there_are_no_matching_results(self):
        class Root(RootType):
            author = single_or_null(lambda: self._join_to_authors(count=0))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_successful_result(data={
            "author": None,
        }))


    def test_single_or_null_relationship_is_resolved_to_object_if_there_is_exactly_one_matching_result(self):
        class Root(RootType):
            author = single_or_null(lambda: self._join_to_authors(count=1))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_successful_result(data={
            "author": {"name": "PG Wodehouse"},
        }))


    def test_single_or_null_relationship_raises_error_if_there_are_multiple_matching_results(self):
        class Root(RootType):
            author = single_or_null(lambda: self._join_to_authors(count=2))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_invalid_result(errors=contains_inanyorder(
            has_string("Expected up to 1 value but got 2"),
        )))


    def test_first_or_null_relationship_is_resolved_to_null_if_there_are_no_matching_results(self):
        class Root(RootType):
            author = first_or_null(lambda: self._join_to_authors(count=0))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_successful_result(data={
            "author": None,
        }))


    def test_first_or_null_relationship_is_resolved_to_object_if_there_is_exactly_one_matching_result(self):
        class Root(RootType):
            author = first_or_null(lambda: self._join_to_authors(count=1))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_successful_result(data={
            "author": {"name": "PG Wodehouse"},
        }))


    def test_first_or_null_relationship_is_resolved_to_first_object_if_there_is_more_than_one_matching_result(self):
        class Root(RootType):
            author = first_or_null(lambda: self._join_to_authors(count=2))

        result = executor(Root)("{ author { name } }")
        assert_that(result, is_successful_result(data={
            "author": {"name": self._FIRST_AUTHOR_NAME},
        }))


    _FIRST_AUTHOR_NAME = "PG Wodehouse"
    _SECOND_AUTHOR_NAME = "Joseph Heller"

    def _join_to_authors(self, count):
        AuthorRecord = attr.make_class("AuthorRecord", ["name"])
        authors = [
            AuthorRecord(self._FIRST_AUTHOR_NAME),
            AuthorRecord(self._SECOND_AUTHOR_NAME),
        ]

        class Author(StaticDataObjectType):
            __records__ = authors[:count]

            name = field(type=String)

        return StaticDataObjectType.select(Author)


def test_relationships_can_take_filter_argument_to_refine_select():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [AuthorRecord("PG Wodehouse"), AuthorRecord("Joseph Heller")]

        name = field(type=String)

    class Root(RootType):
        authors = many(lambda: StaticDataObjectType.select(Author, filter=lambda values: values[:1]))

    result = executor(Root)("{ authors { name } }")
    assert_that(result, is_successful_result(data={
        "authors": [{"name": "PG Wodehouse"}],
    }))


def test_query_builder_can_use_context():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Context(object):
        authors = [AuthorRecord("PG Wodehouse")]

    class Author(StaticDataObjectType):
        name = field(type=String)

    class Root(RootType):
        authors = many(lambda: _join(
            Author,
            lambda root_query, context: context.authors,
            join_fields={},
        ))

    result = executor(Root)("{ authors { name } }", context=Context())
    assert_that(result, is_successful_result(data={
        "authors": [{"name": "PG Wodehouse"}],
    }))


def test_can_extract_fields_from_relationships():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [AuthorRecord("PG Wodehouse"), AuthorRecord("Joseph Heller")]

        name = field(type=String)

    class Root(RootType):
        authors = many(lambda: StaticDataObjectType.select(Author))
        author_names = extract(authors, "name")

    result = executor(Root)("{ authorNames }")
    assert_that(result, is_successful_result(data={
        "authorNames": ["PG Wodehouse", "Joseph Heller"],
    }))


def test_can_extract_fields_from_anonymous_fields():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [AuthorRecord("PG Wodehouse"), AuthorRecord("Joseph Heller")]

        name = field(type=String)

    class Root(RootType):
        author_names = extract(many(lambda: StaticDataObjectType.select(Author)), "name")

    result = executor(Root)("{ authorNames }")
    assert_that(result, is_successful_result(data={
        "authorNames": ["PG Wodehouse", "Joseph Heller"],
    }))


def test_can_extract_fields_from_relationships_using_field():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [AuthorRecord("PG Wodehouse"), AuthorRecord("Joseph Heller")]

        name = field(type=String)

    class Root(RootType):
        authors = many(lambda: StaticDataObjectType.select(Author))
        author_names = extract(authors, lambda: Author.name)

    result = executor(Root)("{ authorNames }")
    assert_that(result, is_successful_result(data={
        "authorNames": ["PG Wodehouse", "Joseph Heller"],
    }))


def test_can_define_custom_fields():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class DoubleField(object):
        def __init__(self, field, type):
            self._field = field
            self.type = type
        
        def immediate_selections(self, parent, selection):
            return (Selection(field=self._field, args={}), )
        
        def create_reader(self, selection, query, context):
            def read(immediates):
                return immediates[0] * 2
            
            return read

    def double_field(field, type):
        return define_field(DoubleField(
            field=field,
            type=type,
        ))

    class Author(StaticDataObjectType):
        __records__ = [AuthorRecord("PG Wodehouse"), AuthorRecord("Joseph Heller")]

        name = field(type=String)
        name_2 = double_field(name, type=String)

    class Root(RootType):
        authors = many(lambda: StaticDataObjectType.select(Author))

    result = executor(Root)("{ authors { name2 } }")
    assert_that(result, is_successful_result(data={
        "authors": [
            {"name2": "PG WodehousePG Wodehouse"},
            {"name2": "Joseph HellerJoseph Heller"},
        ],
    }))


def test_can_implement_graphql_core_interfaces():
    HasName = GraphQLInterfaceType("HasName", fields={
        "name": GraphQLField(GraphQLString),
    }, resolve_type=lambda: None)

    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __interfaces__ = [HasName]

        __records__ = [AuthorRecord("PG Wodehouse")]

        name = field(type=String)

    class Root(RootType):
        author = single(lambda: StaticDataObjectType.select(Author))

    result = executor(Root)("""{
        author {
            ...on HasName {
                name
            }
        }
    }""")
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
    }))


def test_can_implement_declarative_interfaces():
    class HasName(InterfaceType):
        name = field(type=String)

    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __interfaces__ = [HasName]

        __records__ = [AuthorRecord("PG Wodehouse")]

        name = field(type=String)

    class Root(RootType):
        author = single(lambda: StaticDataObjectType.select(Author))

    result = executor(Root)("""{
        author {
            ...on HasName {
                name
            }
        }
    }""")
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
    }))


def test_interfaces_can_be_declared_using_function():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __interfaces__ = lambda: [HasName]

        __records__ = [AuthorRecord("PG Wodehouse")]

        name = field(type=String)

    class HasName(InterfaceType):
        name = field(type=String)

    class Root(RootType):
        author = single(lambda: StaticDataObjectType.select(Author))

    result = executor(Root)("""{
        author {
            ...on HasName {
                name
            }
        }
    }""")
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
    }))


def test_field_type_can_be_declared_using_declarative_interface_type():
    class Author(InterfaceType):
        name = field(type=String)

    class Book(InterfaceType):
        author = field(type=Author)

    assert_that(Book.__graphql__.fields["author"].type, equal_to(Author.__graphql__))


def test_field_type_can_be_declared_using_declarative_object_type():
    class Author(ObjectType):
        name = field(type=String)

        def __fetch_immediates__(cls, selections, query, context):
            pass

    class Book(InterfaceType):
        author = field(type=Author)

    assert_that(Book.__graphql__.fields["author"].type, equal_to(Author.__graphql__))


def test_field_type_can_be_declared_using_declarative_type_in_lambda():
    class Book(InterfaceType):
        author = field(type=lambda: Author)

    class Author(ObjectType):
        name = field(type=String)

        def __fetch_immediates__(cls, selections, query, context):
            pass

    assert_that(Book.__graphql__.fields["author"].type, equal_to(Author.__graphql__))


def test_internal_fields_cannot_be_queried_directly():
    AuthorRecord = attr.make_class("AuthorRecord", ["id", "name"])
    BookRecord = attr.make_class("BookRecord", ["author_id", "title"])

    class Author(StaticDataObjectType):
        __records__ = [
            AuthorRecord("PGW", "PG Wodehouse"),
            AuthorRecord("JH", "Joseph Heller"),
        ]

        id = field(type=String)
        name = field(type=String)

    class Book(StaticDataObjectType):
        __records__ = [
            BookRecord("PGW", "Leave it to Psmith"),
            BookRecord("PGW", "The Code of the Woosters"),
        ]

        author_id = field(type=String, internal=True)
        author = single(lambda: StaticDataObjectType.select(
            Author,
            join={Book.author_id: Author.id},
        ))
        title = field(type=String)

    class Root(RootType):
        books = many(lambda: StaticDataObjectType.select(Book))

    execute = executor(Root)
    assert_that(
        execute("{ books { title authorId } }"),
        is_invalid_result(errors=contains_inanyorder(
            has_string(starts_with('Cannot query field "authorId"')),
        )),
    )
    # Check that internal fields can still be used for joining
    assert_that(
        execute("{ books { title author { name } } }"),
        is_successful_result(data={
            "books": [
                {"title": "Leave it to Psmith", "author": {"name": "PG Wodehouse"}},
                {"title": "The Code of the Woosters", "author": {"name": "PG Wodehouse"}},
            ],
        }),
    )


def test_internal_relationship_fields_cannot_be_queried_directly():
    class Author(StaticDataObjectType):
        __records__ = []
        name = field(type=String)

    class Book(StaticDataObjectType):
        __records__ = []
        title = field(type=String)

    class Root(RootType):
        authors = many(lambda: StaticDataObjectType.select(Author))
        books = many(lambda: StaticDataObjectType.select(Book), internal=True)

    execute = executor(Root)
    assert_that(
        execute("{ books { title } }"),
        is_invalid_result(errors=contains_inanyorder(
            has_string(starts_with('Cannot query field "books"')),
        )),
    )


def test_can_query_fields_extracted_from_internal_fields():
    class Book(StaticDataObjectType):
        __records__ = []
        title = field(type=String)

    class Root(RootType):
        books = many(lambda: StaticDataObjectType.select(Book), internal=True)
        book_titles = extract(books, lambda: Book.title)

    execute = executor(Root)
    assert_that(
        execute("{ bookTitles }"),
        is_successful_result(data={"bookTitles": []}),
    )


def test_field_set_can_be_used_to_declare_multiple_fields_in_one_attribute():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])
    BookRecord = attr.make_class("BookRecord", ["title"])

    class Author(StaticDataObjectType):
        __records__ = [AuthorRecord("PG Wodehouse")]

        name = field(type=String)

    class Book(StaticDataObjectType):
        __records__ = [BookRecord("Leave it to Psmith")]

        title = field(type=String)

    class Root(RootType):
        fields = field_set(
            author=single(lambda: StaticDataObjectType.select(Author)),
            book=single(lambda: StaticDataObjectType.select(Book)),
        )

    result = executor(Root)("{ author { name } book { title } }")
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
        "book": {"title": "Leave it to Psmith"},
    }))


def test_arg_method_can_be_used_as_decorator_to_refine_query():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [
            AuthorRecord("PG Wodehouse"),
            AuthorRecord("Joseph Heller"),
        ]

        name = field(type=String)

    class Root(RootType):
        author = single(lambda: StaticDataObjectType.select(Author))
        @author.arg("nameStartsWith", String)
        def author_arg_starts_with(records, prefix):
            return list(filter(
                lambda record: record.name.startswith(prefix),
                records,
            ))

    result = executor(Root)("""{ author(nameStartsWith: "P") { name } }""")
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
    }))


def test_arg_refiner_can_take_context():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [
            AuthorRecord("PG Wodehouse"),
            AuthorRecord("Joseph Heller"),
        ]

        name = field(type=String)

    class Root(RootType):
        author = single(lambda: StaticDataObjectType.select(Author))
        @author.arg("nameStartsWith", Boolean)
        def author_arg_starts_with(records, _, context):
            return list(filter(
                lambda record: record.name.startswith(context),
                records,
            ))

    result = executor(Root)(
        """{ author(nameStartsWith: true) { name } }""",
        context="P",
    )
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
    }))


def test_can_define_args_directly_on_field():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class DictQuery(object):
        @staticmethod
        def __select_all__():
            return {}

        @staticmethod
        def __add_arg__(args, arg_name, arg_value):
            args[arg_name] = arg_value
            return args

    class Author(ObjectType, DictQuery):
        __records__ = [
            AuthorRecord("PG Wodehouse"),
            AuthorRecord("Joseph Heller"),
        ]

        name = field(type=String)

        @classmethod
        def __fetch_immediates__(cls, selections, query, context):
            records = cls.__records__
            if "nameStartsWith" in query:
                prefix = query["nameStartsWith"]
                records = list(filter(
                    lambda record: record.name.startswith(prefix),
                    records,
                ))

            return [
                tuple(
                    getattr(record, selection.field.attr_name)
                    for selection in selections
                )
                for record in records
            ]

    class Root(RootType):
        author = single(
            lambda: select(Author),
            args={
                "nameStartsWith": String,
            },
        )

    result = executor(Root)("""{ author(nameStartsWith: "P") { name } }""")
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
    }))


def test_fields_can_be_defined_on_superclass():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Named(object):
        name = field(type=String)

    class Author(Named, StaticDataObjectType):
        __records__ = [AuthorRecord("PG Wodehouse")]

    class Root(RootType):
        author = single(lambda: StaticDataObjectType.select(Author))

    result = executor(Root)("{ author { name } }")
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
    }))


def test_can_define_input_object_types():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class AuthorSelection(InputObjectType):
        name_starts_with = field(type=String)

    class Author(StaticDataObjectType):
        __records__ = [
            AuthorRecord("PG Wodehouse"),
            AuthorRecord("Joseph Heller"),
        ]

        name = field(type=String)

    class Root(RootType):
        author = single(lambda: StaticDataObjectType.select(Author))
        @author.arg("selection", AuthorSelection)
        def author_arg_selection(records, selection):
            return list(filter(
                lambda record: record.name.startswith(selection.name_starts_with),
                records,
            ))

    result = executor(Root)("""{ author(selection: {nameStartsWith: "P"}) { name } }""")
    assert_that(result, is_successful_result(data={
        "author": {"name": "PG Wodehouse"},
    }))


def test_explicitly_null_fields_can_be_differentiated_from_undefined_fields():
    SelectionRecord = attr.make_class("SelectionRecord", ["name"])

    class SelectionInput(InputObjectType):
        name = field(type=String)

    class Selection(StaticDataObjectType):
        __records__ = []

        name = field(type=String)

    class Root(RootType):
        selection = single(lambda: StaticDataObjectType.select(Selection))

        @selection.arg("selection", SelectionInput)
        def selection_arg_selection(records, selection):
            return [SelectionRecord(str(selection.name))]

    def run_query(selection):
        return executor(Root)(
            """
                query ($selection: SelectionInput) {
                    selection(selection: $selection) { name }
                }
            """,
            variables={"selection": selection},
        )

    assert_that(run_query({"name": None}), is_successful_result(data={
        "selection": {"name": "None"},
    }))

    assert_that(run_query({}), is_successful_result(data={
        "selection": {"name": "undefined"},
    }))


class TestInputObjectType(object):
    def test_reading_none_returns_none(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        assert_that(
            AuthorSelection.__read__(None),
            equal_to(None),
        )

    def test_field_is_read_from_dict(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        assert_that(
            AuthorSelection.__read__({"nameStartsWith": "Bob"}),
            has_properties(name_starts_with="Bob"),
        )

    def test_raw_value_is_available(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        assert_that(
            AuthorSelection.__read__({"nameStartsWith": "Bob"}),
            has_properties(raw_={"nameStartsWith": "Bob"}),
        )

    def test_non_null_field_is_read_from_dict(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=NonNull(String))

        assert_that(
            AuthorSelection.__read__({"nameStartsWith": "Bob"}),
            has_properties(name_starts_with="Bob"),
        )

    def test_list_field_is_read_from_dict(self):
        class AuthorSelection(InputObjectType):
            names = field(type=List(String))

        assert_that(
            AuthorSelection.__read__({"names": ["Bob"]}),
            has_properties(names=["Bob"]),
        )

    def test_missing_fields_have_value_of_undefined(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        assert_that(
            AuthorSelection.__read__({}),
            has_properties(name_starts_with=undefined),
        )

    def test_when_default_is_set_then_missing_fields_have_default_value(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String, default=None)

        assert_that(
            AuthorSelection.__read__({}),
            has_properties(name_starts_with=None),
        )

    def test_fields_are_recursively_read(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        class BookSelection(InputObjectType):
            author_selection = field(type=AuthorSelection)

        assert_that(
            BookSelection.__read__({"authorSelection": {"nameStartsWith": "Bob"}}),
            has_properties(
                author_selection=has_properties(name_starts_with="Bob"),
            ),
        )

    def test_non_null_fields_are_recursively_read(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        class BookSelection(InputObjectType):
            author_selection = field(type=NonNull(AuthorSelection))

        assert_that(
            BookSelection.__read__({"authorSelection": {"nameStartsWith": "Bob"}}),
            has_properties(
                author_selection=has_properties(name_starts_with="Bob"),
            ),
        )

    def test_list_fields_are_recursively_read(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        class BookSelection(InputObjectType):
            author_selections = field(type=List(AuthorSelection))

        assert_that(
            BookSelection.__read__({"authorSelections": [{"nameStartsWith": "Bob"}]}),
            has_properties(
                author_selections=contains(has_properties(name_starts_with="Bob")),
            ),
        )

    def test_missing_object_type_fields_have_value_of_undefined(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        class BookSelection(InputObjectType):
            author_selection = field(type=AuthorSelection)

        assert_that(
            BookSelection.__read__({}),
            has_properties(author_selection=undefined),
        )

    def test_object_type_field_of_null_is_read_as_none(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        class BookSelection(InputObjectType):
            author_selection = field(type=AuthorSelection)

        assert_that(
            BookSelection.__read__({"authorSelection": None}),
            has_properties(author_selection=None),
        )

    def test_can_instantiate_object_type(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        selection = AuthorSelection(name_starts_with="Bob")

        assert_that(
            selection,
            has_properties(name_starts_with="Bob"),
        )

    def test_unspecified_fields_are_undefined_when_instantiating_input_object_type(self):
        class AuthorSelection(InputObjectType):
            name_starts_with = field(type=String)

        selection = AuthorSelection()

        assert_that(
            selection,
            has_properties(name_starts_with=undefined),
        )

    def test_passing_extra_positional_arguments_raises_an_error(self):
        class AuthorSelection(InputObjectType):
            name = field(type=String)

        pytest.raises(TypeError, lambda: AuthorSelection(1969, name="Bob"))

    def test_passing_extra_keyword_arguments_raises_an_error(self):
        class AuthorSelection(InputObjectType):
            name = field(type=String)

        error = pytest.raises(TypeError, lambda: AuthorSelection(year=1969, name="Bob"))
        assert_that(str(error.value), equal_to("__init__() got an unexpected keyword argument 'year'"))

    def test_str_of_input_objects_shows_name_and_fields(self):
        class Range(InputObjectType):
            start = field(type=Int)
            end = field(type=Int)

        assert_that(str(Range(start=1, end=42)), equal_to("Range(end=42, start=1)"))


def test_undefined_is_falsey():
    assert_that(bool(undefined), equal_to(False))


def test_non_null_type_can_wrap_graphql_core_type():
    assert_that(
        NonNull(GraphQLString).__graphql__,
        all_of(
            instance_of(GraphQLNonNull),
            has_properties(of_type=GraphQLString)
        ),
    )


class TestSnakeCaseToCamelCase(object):
    @pytest.mark.parametrize("snake_case, camel_case", [
        ("one", "one"),
        ("one_two", "oneTwo"),
        ("one_", "one"),
    ])
    def test_string_without_underscores_is_unchanged(self, snake_case, camel_case):
        assert_that(_snake_case_to_camel_case(snake_case), equal_to(camel_case))


def test_name_of_object_type_can_be_overridden():
    class GeneratedType(ObjectType):
        __name__ = "User"

        email_address = field(type=String)
        __fetch_immediates__ = None

    assert_that(GeneratedType.__name__, equal_to("User"))
    assert_that(GeneratedType.__graphql__.of_type.name, equal_to("User"))


def test_name_of_interface_type_can_be_overridden():
    class GeneratedType(InterfaceType):
        __name__ = "User"

        email_address = field(type=String)
        __fetch_immediates__ = None

    assert_that(GeneratedType.__name__, equal_to("User"))
    assert_that(GeneratedType.__graphql__.name, equal_to("User"))


def test_name_of_input_object_type_can_be_overridden():
    class GeneratedType(InputObjectType):
        __name__ = "User"

        email_address = field(type=String)
        __fetch_immediates__ = None

    assert_that(GeneratedType.__name__, equal_to("User"))
    assert_that(GeneratedType.__graphql__.name, equal_to("User"))


def test_query_can_be_executed_with_subschema():
    class Author(StaticDataObjectType):
        __records__ = []

        id = field(type=Int)
        name = field(type=String)

    class Root(RootType):
        author = single_or_null(lambda: StaticDataObjectType.select(Author))

    id_query = "{ author { id } }"
    name_query = "{ author { name } }"
    execute = executor(Root)

    schema_whitelist = parse_schema("""
        schema {
            query: Root
        }

        type Root {
            author: Author
        }

        type Author {
            name: String
        }
    """)

    assert_that(execute(name_query), is_successful_result(data={
        "author": None,
    }))
    assert_that(execute(name_query, schema=schema_whitelist), is_successful_result(data={
        "author": None,
    }))

    assert_that(execute(id_query), is_successful_result(data={
        "author": None,
    }))
    assert_that(execute(id_query, schema=schema_whitelist), is_invalid_result(errors=contains_inanyorder(
        has_string(starts_with('Cannot query field "id"')),
    )))


def test_when_specified_schema_is_not_superschema_then_error_is_raised():
    class Author(StaticDataObjectType):
        __records__ = []

        name = field(type=String)

    class Root(RootType):
        author = single(lambda: StaticDataObjectType.select(Author))

    execute = executor(Root)

    schema_whitelist = parse_schema("""
        schema {
            query: Root
        }

        type Root {
            author: Author
        }

        type Author {
            id: Int
            name: String
        }
    """)

    query = """{
        author {
            name
        }
    }"""

    error = pytest.raises(ValueError, lambda: execute(query, schema=schema_whitelist))
    assert_that(str(error.value), equal_to("schema argument must be superschema of main schema"))


def test_variables_are_validated():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [
            AuthorRecord("PG Wodehouse"),
            AuthorRecord("Joseph Heller"),
        ]

        name = field(type=String)

    class AuthorSelection(InputObjectType):
        limit = field(type=Int, default=None)

    class Root(RootType):
        authors = many(lambda: StaticDataObjectType.select(Author))

        @authors.arg("selection", AuthorSelection)
        def authors_arg_selection(records, selection):
            if selection.name is not None:
                records = list(filter(
                    lambda record: record.name == selection.name,
                    records,
                ))
            return records

    execute = executor(Root)
    query = """query ($selection: AuthorSelection!) { authors(selection: $selection) { name } }"""
    variables = {"selection": {"name": "PG Wodehouse"}}

    result = execute(query, variables=variables)
    assert_that(result, is_invalid_result(errors=contains_inanyorder(
        has_string(equal_to('Variable "$selection" got invalid value {"name": "PG Wodehouse"}.\nIn field "name": Unknown field.')),
    )))


def test_variables_are_validated_against_whitelist():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [
            AuthorRecord("PG Wodehouse"),
            AuthorRecord("Joseph Heller"),
        ]

        name = field(type=String)

    class AuthorSelection(InputObjectType):
        limit = field(type=Int, default=None)
        name = field(type=String, default=None)

    class Root(RootType):
        authors = many(lambda: StaticDataObjectType.select(Author))

        @authors.arg("selection", AuthorSelection)
        def authors_arg_selection(records, selection):
            if selection.name is not None:
                records = list(filter(
                    lambda record: record.name == selection.name,
                    records,
                ))
            return records

    execute = executor(Root)
    query = """query ($selection: AuthorSelection!) { authors(selection: $selection) { name } }"""
    variables = {"selection": {"name": "PG Wodehouse"}}

    result = execute(query, variables=variables)
    assert_that(result, is_successful_result(data={
        "authors": [{"name": "PG Wodehouse"}],
    }))

    schema_whitelist = parse_schema("""
        schema {
            query: Root
        }

        type Root {
            authors(selection: AuthorSelection): [Author]
        }

        input AuthorSelection {
            limit: Int
        }

        type Author {
            name: String
        }
    """)

    result = execute(query, variables=variables, schema=schema_whitelist)
    assert_that(result, is_invalid_result(errors=contains_inanyorder(
        has_string(equal_to('Variable "$selection" got invalid value {"name": "PG Wodehouse"}.\nIn field "name": Unknown field.')),
    )))


def test_can_read_fields_of_input_object_types():
    class UserInput(InputObjectType):
        username = field(type=String)
        email_address = field(type=String)

    assert_that(fields(UserInput), contains_inanyorder(
        has_properties(attr_name="username", field_name="username"),
        has_properties(attr_name="email_address", field_name="emailAddress"),
    ))


def test_variables_can_be_none():
    AuthorRecord = attr.make_class("AuthorRecord", ["name"])

    class Author(StaticDataObjectType):
        __records__ = [
            AuthorRecord("PG Wodehouse"),
            AuthorRecord("Joseph Heller"),
        ]

        name = field(type=String)

    class Root(RootType):
        authors = many(lambda: StaticDataObjectType.select(Author))

        @authors.arg("name", String)
        def authors_arg_selection(records, name):
            if name is not None:
                records = list(filter(
                    lambda record: record.name == name,
                    records,
                ))
            return records

    execute = executor(Root)
    query = """query ($name: String) { authors(name: $name) { name } }"""

    assert_that(
        execute(query, variables={"name": "PG Wodehouse"}),
        is_successful_result(data={
            "authors": [{"name": "PG Wodehouse"}],
        }),
    )

    assert_that(
        execute(query, variables=None),
        is_successful_result(data={
            "authors": [{"name": "PG Wodehouse"}, {"name": "Joseph Heller"}],
        }),
    )

def test_fields_are_in_alphabetical_ordering():
    class Root(RootType):
        value_b = field(type=Int)
        value_a = field(type=Int)
        value_c = field(type=Int)


    execute = executor(Root)
    query = """
        query {
            __schema {
                queryType {
                    fields {
                        name
                    }
                }
            }
        }
    """

    assert_that(
        execute(query),
        is_successful_result(data={
            "__schema": {
                "queryType": {
                    "fields": [
                        {"name": "valueA"},
                        {"name": "valueB"},
                        {"name": "valueC"},
                    ],
                },
            },
        }),
    )
