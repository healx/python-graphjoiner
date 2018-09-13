import collections
from copy import copy

from graphql.language import ast as ast_types
from graphql.execution.values import get_argument_values
from graphql.type.directives import GraphQLIncludeDirective, GraphQLSkipDirective
from six.moves import filter

from .util import find, single


class DocumentRequest(object):
    def __init__(self, query, schema_query):
        self.query = query
        self.schema_query = schema_query


class Request(object):
    def __init__(self, key, field, args, selections, join_selections):
        self.key = key
        self.field = field
        self.args = args
        self.selections = selections
        self.join_selections = join_selections

    def copy(self, **kwargs):
        attrs = dict(
            key=self.key,
            field=self.field,
            args=self.args,
            selections=self.selections,
            join_selections=self.join_selections,
        )
        attrs.update(**kwargs)
        return Request(**attrs)


def request_from_graphql_document(document, query_root, mutation_root, variables):
    fragments = dict(
        (definition.name.value, definition)
        for definition in document.definitions
        if isinstance(definition, ast_types.FragmentDefinition)
    )
    definition_index, operation = single(list(filter(
        lambda pair: isinstance(pair[1], ast_types.OperationDefinition),
        enumerate(document.definitions)
    )))

    if operation.operation == "mutation":
        root = mutation_root
    else:
        root = query_root

    schema_selection = find(
        lambda selection: selection.name.value == "__schema",
        operation.selection_set.selections,
    )

    if schema_selection is None:
        schema_query = None
    else:
        schema_query_definition = copy(operation)
        schema_query_definition.selection_set = copy(schema_query_definition.selection_set)
        schema_query_definition.selection_set.selections = [schema_selection]

        schema_query = copy(document)
        schema_query.definitions = copy(schema_query.definitions)
        schema_query.definitions[definition_index] = schema_query_definition

    return DocumentRequest(
        query=request_from_graphql_ast(operation, root, variables=variables, fragments=fragments, field=None),
        schema_query=schema_query,
    )


def request_from_graphql_ast(ast, root, variables, field, fragments):
    if isinstance(ast, ast_types.Field):
        key = field_key(ast)
    else:
        key = None

    if field is None:
        args = {}
    else:
        args = get_argument_values(field.args, getattr(ast, "arguments", []), variables=variables)

    selections = _graphql_selections(ast, root, variables=variables, fragments=fragments)

    return Request(
        key=key,
        field=field,
        args=args,
        selections=selections,
        join_selections=(),
    )


def _field_name(ast):
    return ast.name.value


def field_key(ast):
    if ast.alias is None:
        return _field_name(ast)
    else:
        return ast.alias.value



def _graphql_selections(ast, root, variables, fragments):
    if ast.selection_set is None:
        return None
    else:
        fields = root.fields()

        field_selections = _merge_fields(_collect_fields(ast, fragments=fragments, variables=variables))

        return [
            _request_from_selection(
                selection,
                variables=variables,
                fragments=fragments,
                field=fields[_field_name(selection)]
            )
            for selection in field_selections
            if _field_name(selection) != "__schema"
        ]


def _collect_fields(ast, fragments, variables):
    field_selections = []

    _add_fields(ast, field_selections, fragments=fragments, variables=variables)

    return field_selections

def _add_fields(ast, field_selections, fragments, variables):
    for selection in ast.selection_set.selections:
        if _should_include_node(selection, variables=variables):
            if isinstance(selection, ast_types.Field):
                field_selections.append(selection)
            elif isinstance(selection, ast_types.FragmentSpread):
                # TODO: handle type conditions
                _add_fields(fragments[selection.name.value], field_selections, fragments=fragments, variables=variables)
            elif isinstance(selection, ast_types.InlineFragment):
                _add_fields(selection, field_selections, fragments=fragments, variables=variables)
            else:
                raise Exception("Unknown selection: {}".format(type(selection)))


def _should_include_node(node, variables):
    for directive in node.directives:
        name = directive.name.value
        if name == "skip":
            args = get_argument_values(GraphQLSkipDirective.args, directive.arguments, variables)
            if args.get("if") is True:
                return False
        elif name == "include":
            args = get_argument_values(GraphQLIncludeDirective.args, directive.arguments, variables)
            if args.get("if") is False:
                return False
        else:
            raise Exception("Unknown directive: {}".format(name))

    return True


def _merge_fields(selections):
    # TODO: validation

    merged = collections.OrderedDict()

    for selection in selections:
        key = field_key(selection)
        if key in merged:
            if selection.selection_set is not None:
                merged[key] = copy(merged[key])
                merged[key].selection_set = copy(merged[key].selection_set)
                merged[key].selection_set.selections += selection.selection_set.selections
        else:
            merged[key] = selection

    return merged.values()


def _request_from_selection(selection, field, variables, fragments):
    return request_from_graphql_ast(
        selection,
        variables=variables,
        fragments=fragments,
        field=field,
        root=field.target,
    )

