"""The `merge` materialization, for models a top-up build extends instead of rebuilding.

A model of this kind names a change table and how its rows merge:

    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.changes', add = 'listing_id, response_id')
    )

The change table, `ads.changes` or `ads.touched`, has a boolean column `incremental`.

- In a full build it holds every answer or ad with `incremental` false. The materialization then
  replaces the model's table with the query's rows, as for a FULL model.
- In a top-up build it holds only the new answers, or the ads they change, with `incremental`
  true, and it may be empty. The model's query reads only the rows of those answers or ads.
  On the first insert into the new table, the materialization copies the rows of the table the
  prod view still points to, the one the previous build made, and merges in the query's rows:
  - `add = 'COLUMNS'`: it keeps every previous row and adds each query row whose key is new.
    The rows of a key depend on that key's inputs alone, which a top-up never alters, as for
    an answer, a distinct record or a distinct unit history.
  - `replace = 'COLUMN'`: it drops the previous rows whose column, read as text, matches a
    `listing_id` of the change table, and adds all the query rows.

`ops/pipeline/build.py` turns on top-up builds only when every model above and in this kind
has the definition of the prod build's, so the rows it copies match what a full build would
give.
"""

from sqlglot import exp
from sqlmesh import CustomMaterialization
from sqlmesh.utils.errors import SQLMeshError


class Merge(CustomMaterialization):
    NAME = "merge"

    def insert(
        self, table_name, query_or_df, model, is_first_insert, render_kwargs, **kwargs
    ):
        changes = self._changes(model, kwargs)
        if changes is None:
            self._replace_query_for_model(
                model, table_name, query_or_df, render_kwargs, **kwargs
            )
            return
        target = _sql(table_name)
        properties = model.kind.materialization_properties
        replace = properties.get("replace")
        if is_first_insert:
            previous = _sql(model.fqn)
            if not self.adapter.table_exists(model.fqn):
                raise SQLMeshError(
                    f"a top-up build of {model.name} needs a previous table at {previous}"
                )
            kept = f"SELECT p.* FROM {previous} p"
            if replace:
                kept += f" ANTI JOIN {changes} c ON p.{replace}::VARCHAR = c.listing_id"
            self.adapter.replace_query(
                table_name, exp.maybe_parse(kept, dialect=self.adapter.dialect)
            )
        elif replace:
            # A second evaluation of the same table: the rows of the changed ads come again.
            self.adapter.execute(
                f"DELETE FROM {target} WHERE {replace}::VARCHAR IN "
                f"(SELECT listing_id FROM {changes})"
            )
        self._add(table_name, query_or_df, model, render_kwargs)

    def append(self, table_name, query_or_df, model, render_kwargs, **kwargs):
        if self._changes(model, kwargs) is None:
            super().append(table_name, query_or_df, model, render_kwargs, **kwargs)
        else:
            self._add(table_name, query_or_df, model, render_kwargs)

    def _changes(self, model, kwargs):
        """The change table's name in a top-up build, or None in a full build."""
        name = model.kind.materialization_properties["changes"]
        index = kwargs["deployability_index"]
        found = [
            s
            for s in kwargs["snapshots"].values()
            if s.is_model and s.model.name == name
        ]
        if len(found) != 1:
            raise SQLMeshError(f"{model.name} reads no change table {name}")
        table = _sql(found[0].table_name(index.is_representative(found[0])))
        row = self.adapter.fetchone(
            f"SELECT coalesce(bool_and(incremental), true) FROM {table}"
        )
        return table if row[0] else None

    def _add(self, table_name, query_or_df, model, render_kwargs):
        columns, sources = self._get_target_and_source_columns(
            model, table_name, render_kwargs=render_kwargs
        )
        add = model.kind.materialization_properties.get("add")
        if not add:
            self.adapter.insert_append(
                table_name,
                query_or_df,
                target_columns_to_types=columns,
                source_columns=sources,
            )
            return
        target = _sql(table_name)
        with self.adapter.temp_table(
            query_or_df,
            name=table_name,
            target_columns_to_types=columns,
            source_columns=sources,
        ) as temp:
            self.adapter.execute(
                f"INSERT INTO {target} BY NAME SELECT t.* FROM {_sql(temp)} t "
                f"ANTI JOIN {target} USING ({add})"
            )


def _sql(table):
    return exp.to_table(table, dialect="duckdb").sql(dialect="duckdb")
