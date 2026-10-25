"""Bounded Agent Skills package inspection. Never imports or executes scripts."""

from dataclasses import dataclass
from pathlib import Path
import re

import yaml

from core.project_snapshot import ProjectSnapshot, SnapshotFile, SnapshotLimits, relative_name


class SkillPackageError(ValueError):
    pass


class MetadataLoader(yaml.SafeLoader):
    def __init__(self, stream):
        super().__init__(stream)
        self.node_count = 0
        self.node_depth = 0

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise SkillPackageError("Aliases YAML não são permitidos.")
        self.node_count += 1
        self.node_depth += 1
        try:
            if self.node_count > 256 or self.node_depth > 8:
                raise SkillPackageError("Metadados YAML excedem limites de complexidade.")
            return super().compose_node(parent, index)
        finally:
            self.node_depth -= 1

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, yaml.MappingNode):
            raise SkillPackageError("Metadados devem ser um mapa.")
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise SkillPackageError("Chave YAML inválida ou duplicada.")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    license: str = ""
    compatibility: str = ""
    metadata: tuple = ()
    allowed_tools: str = ""  # Declaration only: never a permission grant.


def parse_skill_document(content, folder_name):
    if not isinstance(content, bytes) or len(content) > 65536:
        raise SkillPackageError("SKILL.md deve ter até 64 KiB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError as error:
        raise SkillPackageError("SKILL.md deve usar UTF-8.") from error
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise SkillPackageError("SKILL.md exige frontmatter YAML.")
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None:
        raise SkillPackageError("Frontmatter sem delimitador final.")
    frontmatter = "".join(lines[1:end])
    if len(frontmatter.encode("utf-8")) > 8192:
        raise SkillPackageError("Frontmatter excede 8 KiB.")
    try:
        fields = yaml.load(frontmatter, Loader=MetadataLoader)
    except yaml.YAMLError as error:
        raise SkillPackageError("Frontmatter YAML inválido ou com tags não permitidas.") from error
    permitted = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    if not isinstance(fields, dict) or set(fields) - permitted:
        raise SkillPackageError("Campos de frontmatter desconhecidos; use metadata para extensões.")
    name = fields.get("name")
    if (not isinstance(name, str) or len(name) > 64
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or name != folder_name):
        raise SkillPackageError("Nome inválido ou diferente da pasta do pacote.")
    for key, maximum, required in (("description", 1024, True), ("license", 1024, False),
                                   ("compatibility", 500, False), ("allowed-tools", 2048, False)):
        value = fields.get(key, "")
        if not isinstance(value, str) or len(value) > maximum or ((required or key in fields) and not value.strip()):
            raise SkillPackageError(f"Campo inválido: {key}.")
    metadata = fields.get("metadata", {})
    if not isinstance(metadata, dict) or len(metadata) > 32 or any(
        not isinstance(key, str) or not isinstance(value, str) or len(key) > 100 or len(value) > 1000
        for key, value in metadata.items()
    ):
        raise SkillPackageError("metadata exige até 32 pares de texto limitados.")
    return SkillMetadata(name, fields["description"], fields.get("license", ""),
                         fields.get("compatibility", ""), tuple(sorted(metadata.items())),
                         fields.get("allowed-tools", "")), "".join(lines[end + 1:])


@dataclass(frozen=True)
class SkillPackage:
    metadata: SkillMetadata
    instructions: str
    snapshot: ProjectSnapshot

    @classmethod
    def from_snapshot(cls, snapshot, folder_name):
        if len(snapshot.files) > 64 or sum(len(item.content) for item in snapshot.files) > 4 * 1024 * 1024:
            raise SkillPackageError("Pacote excede 64 arquivos ou 4 MiB.")
        if any(len(item.content) > 256 * 1024 for item in snapshot.files):
            raise SkillPackageError("Arquivo do pacote excede 256 KiB.")
        document = next((item.content for item in snapshot.files if item.name == "SKILL.md"), None)
        if document is None:
            raise SkillPackageError("Pacote sem SKILL.md na raiz.")
        metadata, body = parse_skill_document(document, folder_name)
        return cls(metadata, body, snapshot)

    @classmethod
    def capture(cls, directory, *, cancelled=lambda: False):
        directory = Path(directory).absolute()
        snapshot = ProjectSnapshot.capture(directory, cancelled=cancelled, limits=SnapshotLimits(
            files=64, entries=1024, bytes=4 * 1024 * 1024, file_bytes=256 * 1024, depth=8))
        return cls.from_snapshot(snapshot, directory.name)

    def read_text(self, name):
        name = relative_name(name)
        item = next((item for item in self.snapshot.files if item.name == name), None)
        if item is None:
            raise SkillPackageError("Recurso ausente no pacote capturado.")
        if len(item.content) > 16384:
            raise SkillPackageError("Recurso excede 16 KiB para leitura textual.")
        try:
            return item.content.decode("utf-8")
        except UnicodeError as error:
            raise SkillPackageError("Recurso não é texto UTF-8.") from error

    def export_zip(self, destination):
        # Named root preserves the required directory/name relationship on extraction.
        package = ProjectSnapshot(tuple(SnapshotFile(self.metadata.name + "/" + item.name, item.content)
                                        for item in self.snapshot.files))
        return package.export_zip(destination)
