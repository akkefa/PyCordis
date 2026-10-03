"""Plugins imported explicitly by the loader example."""

from pycordis import Context, PluginMeta, Service, ValidationError, ValidationIssue, plugin_meta


class DatabaseConfig:
    def validate(self, value: object) -> object:
        if value is None:
            return {"timeout": 5}
        if not isinstance(value, dict):
            raise ValidationError([ValidationIssue("expected an object")])
        return {"timeout": 5, **value}


@plugin_meta(PluginMeta(config=DatabaseConfig()))
class Database(Service):
    name = "database"

    def start(self) -> None:
        print("Database ready:", self.config)


@plugin_meta(PluginMeta(inject=["database"]))
def worker(ctx: Context, config: object) -> object:
    assert isinstance(ctx.require("database"), Database)
    print("Worker ready:", config)
    return lambda: print("Worker released")
