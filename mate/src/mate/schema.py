"""Data model of the MATE corpus (Messages, Attachments, Threads and Evidence; working name).

The corpus is a set of JSON Lines tables, one per entity below, plus the files of the
attachments and the rendered mail (``rendered/``). Each table is the single source of truth
for its entity; everything that can be derived (thread chains, copies, the typed graph) is
computed in ``mate.corpus`` and checked in ``mate.validate`` instead of being stored twice.

Four layers, kept apart on purpose (design document, section B):

- world: organisations, people, projects;
- knowledge: facts and their values over time (what is true, and when);
- artifacts: a document (artifact), its states (versions) and each time a version is carried
  by a message (occurrence), with the role it has there;
- communication: threads and messages.

Evidence spans tie the knowledge layer to the other two: every place where a fact value is
stated, copies included. Questions point to groups of spans, one group per value they need.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"


def _id(prefix: str) -> type[str]:
    """A string id with a fixed prefix: lower case, digits and hyphens."""
    return Annotated[str, Field(pattern=rf"^{prefix}-[a-z0-9][a-z0-9-]*$")]  # type: ignore[return-value]


OrgId = _id("org")
PersonId = _id("per")
ProjectId = _id("prj")
FactId = _id("fct")
FactValueId = _id("fv")
ArtifactId = _id("art")
VersionId = _id("ver")
ThreadId = _id("thr")
MessageId = _id("msg")
OccurrenceId = _id("occ")
SpanId = _id("spn")
RelationId = _id("rel")
InjectionId = _id("inj")
QuestionId = _id("q")

Lang = Literal["de", "en"]

# Reserved for documentation (RFC 2606): no generated address can reach a real mailbox.
EXAMPLE_DOMAIN = r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.example$"


class Model(BaseModel):
    """Base of every record: unknown fields are errors, enums are stored as their values."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ----------------------------------------------------------------------------- world


class OrgKind(str, Enum):
    internal = "internal"
    customer = "customer"
    supplier = "supplier"
    partner = "partner"
    service = "service"  # newsletters, IT notifications: the background mail


class Organisation(Model):
    id: OrgId
    name: str
    domain: Annotated[str, Field(pattern=EXAMPLE_DOMAIN)]
    kind: OrgKind
    language: Lang
    disclaimer: str | None = None  # legal footer appended to every outgoing message


class Person(Model):
    id: PersonId
    name: str
    email: str
    org_id: OrgId
    title: str
    # 0 external or informal, 1 staff, 2 owner of the topic, 3 approver. Used to resolve
    # authority conflicts (a rumour forwarded by staff against the owner's document).
    authority: Annotated[int, Field(ge=0, le=3)] = 1
    languages: list[Lang] = Field(min_length=1)
    signature: str | None = None


class Project(Model):
    id: ProjectId
    name: str
    codename: str | None = None  # internal jargon, which lexical retrieval needs and dense may miss
    owner_org_id: OrgId
    language: Lang
    start: date
    end: date | None = None
    description: str
    kind: Literal["project", "background"] = "project"


# ------------------------------------------------------------------------- knowledge


class ValueType(str, Enum):
    money = "money"
    date = "date"
    duration = "duration"
    quantity = "quantity"
    identifier = "identifier"
    text = "text"
    person = "person"
    boolean = "boolean"


class Fact(Model):
    """A variable of the world that can take values over time: "unit price of pump P-200"."""

    id: FactId
    project_id: ProjectId
    subject: str
    attribute: str
    value_type: ValueType
    unit: str | None = None
    description: str | None = None


class Standing(str, Enum):
    valid = "valid"  # true in its validity interval
    contested = "contested"  # contradicted by another value, never resolved: report both
    erroneous = "erroneous"  # stated but wrong, resolved by authority: do not report as true


class FactValue(Model):
    id: FactValueId
    fact_id: FactId
    value: str | int | float | bool  # canonical: decimal string with unit, ISO date, ...
    # How the value is written, per language. The first form is the one the generator plants;
    # all forms are accepted when an answer is graded. Every span anchor is one of them.
    surfaces: dict[Lang, list[str]]
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None  # set when a later value supersedes this one
    supersedes: FactValueId | None = None
    standing: Standing = Standing.valid
    asserted_by: PersonId | None = None


# ------------------------------------------------------------------------- artifacts


class ArtifactKind(str, Enum):
    offer = "offer"
    order = "order"
    invoice = "invoice"
    contract = "contract"
    specification = "specification"
    drawing = "drawing"
    test_report = "test_report"
    minutes = "minutes"
    report = "report"
    presentation = "presentation"
    spreadsheet = "spreadsheet"
    chart = "chart"
    photo = "photo"
    screenshot = "screenshot"
    delivery_note = "delivery_note"
    certificate = "certificate"
    logo = "logo"
    other = "other"


class Modality(str, Enum):
    """How the content of a version can be read; the stratification axis of RQ3 (C4)."""

    text_document = "text_document"  # born-digital PDF, DOCX: a text layer exists
    slides = "slides"
    spreadsheet = "spreadsheet"
    scanned_document = "scanned_document"  # image-only PDF or TIFF: needs OCR or a visual model
    chart_image = "chart_image"
    photo = "photo"
    screenshot = "screenshot"
    decorative_image = "decorative_image"  # logos and signature images: noise for retrieval


class Artifact(Model):
    id: ArtifactId
    project_id: ProjectId | None = None
    kind: ArtifactKind
    title: str
    owner: PersonId


class FileRef(Model):
    path: str  # relative to the corpus root, forward slashes
    media_type: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    bytes: Annotated[int, Field(gt=0)]
    pages: int | None = None


class Degradation(Model):
    """How a scan or photo was degraded, so that OCR difficulty is a known, reportable factor."""

    dpi: int
    noise: Annotated[float, Field(ge=0, le=1)]
    skew_degrees: float = 0.0
    jpeg_quality: int | None = None


class ArtifactVersion(Model):
    id: VersionId
    artifact_id: ArtifactId
    label: str  # as people write it: "v2", "Rev. C", "final"
    created_at: AwareDatetime
    author: PersonId
    modality: Modality
    file: FileRef
    supersedes: VersionId | None = None
    change_note: str | None = None
    # Text that is only in the pixels (chart labels, a scanned page), kept so that anchors of
    # image spans can be checked and OCR output can be scored.
    text_in_image: list[str] = Field(default_factory=list)
    degradation: Degradation | None = None


# --------------------------------------------------------------------- communication


class ThreadKind(str, Enum):
    project = "project"
    background = "background"  # unrelated work mail: distractors
    newsletter = "newsletter"
    notification = "notification"


class Thread(Model):
    id: ThreadId
    project_id: ProjectId | None = None
    subject: str
    language: Lang
    kind: ThreadKind = ThreadKind.project


class MessageKind(str, Enum):
    new = "new"
    reply = "reply"
    reply_all = "reply_all"
    forward = "forward"
    resend = "resend"  # the same content sent again ("sorry, forgot the attachment")
    auto_reply = "auto_reply"
    newsletter = "newsletter"
    notification = "notification"


class QuoteStyle(str, Enum):
    """How a client writes the history under a reply; it decides what byte-exact deduplication sees."""

    outlook_header = "outlook_header"  # "-----Original Message-----" + header lines, text unchanged
    prefix_gt = "prefix_gt"  # "On ... wrote:" + every line prefixed with "> "
    none = "none"  # history cut


class Quote(Model):
    message_id: MessageId
    style: QuoteStyle


class Body(Model):
    # The author's new text. An inline image sits where its placeholder {{img:<occurrence id>}} is.
    text: str
    signature: bool = True
    disclaimer: bool = True  # the sender's organisation footer, if it has one
    quote: Quote | None = None  # replies and forwards: the history written under the new text
    html: bool = True  # send a text/html alternative (needed for inline images)


class Message(Model):
    id: MessageId
    rfc_message_id: Annotated[str, Field(pattern=r"^<[^<>@\s]+@[a-z0-9.-]+\.example>$")]
    thread_id: ThreadId
    kind: MessageKind
    in_reply_to: MessageId | None = None
    forward_of: MessageId | None = None
    sender: PersonId
    to: list[PersonId] = Field(min_length=1)
    cc: list[PersonId] = Field(default_factory=list)
    # Blind copies are part of the truth but never of the delivered mail: like a real server,
    # the renderer writes no Bcc header, so no system under test can see them.
    bcc: list[PersonId] = Field(default_factory=list)
    sent_at: AwareDatetime
    subject: str  # as sent, with "Re:", "AW:", "Fwd:", "WG:"
    language: Lang
    body: Body


class Role(str, Enum):
    """The role of an occurrence in its message: the distinction claim C3 says is untreated."""

    appended = "appended"  # Content-Disposition: attachment
    inline = "inline"  # cid: image placed in the HTML body, part of the message's content
    inline_decorative = "inline_decorative"  # logos, signature images: no content
    forwarded_embedded = "forwarded_embedded"  # inside an attached message/rfc822
    link_only = "link_only"  # "the file is on the share": named, not carried


class Occurrence(Model):
    """One version carried by one message, with the role it has there."""

    id: OccurrenceId
    message_id: MessageId
    version_id: VersionId
    role: Role
    filename: str  # as sent, which need not be the canonical name ("Angebot (2).pdf")
    content_id: str | None = None  # inline images only
    order: Annotated[int, Field(ge=0)]  # position among the message's file parts, as written


# -------------------------------------------------------------------------- evidence


class LocKind(str, Enum):
    header = "header"  # From, To, Date: who and when
    subject = "subject"
    body = "body"  # the author's new text
    quoted_body = "quoted_body"  # history under a reply: a copy
    forwarded_body = "forwarded_body"  # history under a forward: a copy
    file = "file"  # inside an attachment version: text, table cell or pixels


class Location(Model):
    kind: LocKind
    message_id: MessageId | None = None  # header, subject and body kinds
    version_id: VersionId | None = None  # file kind
    page: int | None = None  # 1-based, for paged files
    part: Literal["text", "table", "image", "caption"] | None = None
    region: str | None = None  # free locator: "table Preise, row P-200", "y axis"


class SpanOrigin(str, Enum):
    original = "original"  # first statement of the value at this place
    quoted = "quoted"  # copied by a reply's history
    forwarded = "forwarded"  # copied by a forward
    restated = "restated"  # stated again in other words, by the same or another author


class Span(Model):
    """A place where a fact value is stated, or a sentence that refers to an attachment."""

    id: SpanId
    fact_value_id: FactValueId | None = None  # None: a reference sentence ("see the revised offer")
    location: Location
    anchor: Annotated[str, Field(min_length=1, max_length=80)]  # exact text at that place
    origin: SpanOrigin = SpanOrigin.original
    copy_of: SpanId | None = None
    derived: bool = False  # created by the renderer (copies in quoted and forwarded history)


class RefKind(str, Enum):
    message = "message"
    occurrence = "occurrence"
    version = "version"
    artifact = "artifact"
    span = "span"
    fact_value = "fact_value"
    thread = "thread"


class Ref(Model):
    kind: RefKind
    id: str


class RelType(str, Enum):
    """Typed links that are not already fields; replies, forwards and supersession are fields."""

    refers_to = "REFERS_TO"  # a sentence (span) points at an occurrence
    contradicts = "CONTRADICTS"  # two values of one fact disagree with no supersession
    near_copy_of = "NEAR_COPY_OF"  # a message or version that is almost the same as another
    derived_from = "DERIVED_FROM"  # minutes summarising a thread, a chart made from a table


class Relation(Model):
    id: RelationId
    type: RelType
    source: Ref
    target: Ref
    attrs: dict[str, str | int | float | bool] = Field(default_factory=dict)


class InjectionKind(str, Enum):
    resend = "resend"
    forward_copy = "forward_copy"
    near_copy = "near_copy"
    boilerplate = "boilerplate"
    distractor_thread = "distractor_thread"
    lookalike_project = "lookalike_project"
    supersession = "supersession"
    contradiction = "contradiction"
    erroneous_claim = "erroneous_claim"
    image_text_conflict = "image_text_conflict"
    auto_reply = "auto_reply"
    newsletter = "newsletter"


class Injection(Model):
    """One planned difficulty, logged so every label can be audited back to its cause."""

    id: InjectionId
    kind: InjectionKind
    targets: list[Ref] = Field(min_length=1)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)
    note: str | None = None


# ------------------------------------------------------------------------- questions


class QType(str, Enum):
    fact_body = "fact_body"
    fact_attachment = "fact_attachment"
    fact_image = "fact_image"
    msg_to_attachment = "msg_to_attachment"
    attachment_to_msg = "attachment_to_msg"
    current_value = "current_value"
    as_of_value = "as_of_value"
    value_history = "value_history"
    contested = "contested"
    authority_conflict = "authority_conflict"
    image_text_conflict = "image_text_conflict"
    count_distinct = "count_distinct"
    thread_summary = "thread_summary"
    metadata = "metadata"
    unanswerable = "unanswerable"


QTYPE_FAMILY: dict[str, str] = {
    "fact_body": "lookup",
    "fact_attachment": "lookup",
    "fact_image": "lookup",
    "msg_to_attachment": "coupling",
    "attachment_to_msg": "coupling",
    "current_value": "temporal",
    "as_of_value": "temporal",
    "value_history": "temporal",
    "contested": "conflict",
    "authority_conflict": "conflict",
    "image_text_conflict": "conflict",
    "count_distinct": "aggregation",
    "thread_summary": "aggregation",
    "metadata": "metadata",
    "unanswerable": "abstention",
}


class Scope(str, Enum):
    current = "current"  # true now (at asked_at)
    as_of = "as_of"  # true at an earlier date
    history = "history"  # how it changed
    none = "none"  # not time-dependent


class AnswerKind(str, Enum):
    value = "value"
    values = "values"
    count = "count"
    boolean = "boolean"
    person = "person"
    date = "date"
    summary = "summary"
    contested = "contested"  # the right answer names both values and that they disagree
    abstain = "abstain"


class Answer(Model):
    kind: AnswerKind
    reference_text: str
    accepted: list[str] = Field(default_factory=list)  # value strings a correct answer contains
    superseded: list[str] = Field(default_factory=list)  # closed pool for version grading
    fact_value_ids: list[FactValueId] = Field(default_factory=list)


class EvidenceGroup(Model):
    """One distinct piece of evidence the answer needs, with every place it can be found."""

    fact_value_id: FactValueId | None = None
    span_ids: list[SpanId] = Field(min_length=1)
    required: bool = True


class Gold(Model):
    groups: list[EvidenceGroup] = Field(default_factory=list)
    # Attachments whose content the answer needs: attribution fails if none of them (or a
    # copy) is used, even when the answer text is right.
    required_occurrences: list[OccurrenceId] = Field(default_factory=list)
    min_coverage: Annotated[float, Field(gt=0, le=1)] | None = None  # summaries: share of groups


class Variant(Model):
    style: Literal["indirect", "verbose", "formal", "keyword", "colloquial"]
    text: str


class Strata(Model):
    evidence_location: Literal["body", "attachment", "image", "header", "mixed", "none"]
    role: Literal["appended", "inline", "mixed", "none"] = "none"
    modality: Modality | None = None
    version_state: Literal["single", "current_of_n", "historical_of_n", "none"] = "none"
    n_versions: int = 1
    n_copies: int = 0  # extra places the needed evidence is copied to
    direction: Literal["m2a", "a2m", "none"] = "none"
    hops: int = 1


class Check(Model):
    by: Literal["auto", "llm", "saad", "chourouk"]
    check: str
    passed: bool


class Question(Model):
    id: QuestionId
    project_id: ProjectId
    language: Lang
    type: QType
    asked_at: AwareDatetime  # the reference "now" of the question
    scope: Scope
    as_of: AwareDatetime | None = None
    asker: PersonId | None = None
    text: str
    variants: list[Variant] = Field(default_factory=list)
    answer: Answer
    gold: Gold
    strata: Strata
    template: str | None = None
    checks: list[Check] = Field(default_factory=list)


# ---------------------------------------------------------------------------- corpus


class Manifest(Model):
    name: str
    schema_version: str = SCHEMA_VERSION
    corpus_version: str
    created_at: AwareDatetime
    seed: int
    generator: str
    languages: list[Lang]
    licence: str
    counts: dict[str, int] = Field(default_factory=dict)
    splits: dict[Literal["dev", "test"], list[ProjectId]] = Field(default_factory=dict)
    files_sha256: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------- runs


class Retrieved(Model):
    """One retrieved passage as a system under test returns it."""

    rank: Annotated[int, Field(ge=1)]
    score: float | None = None
    text: str
    rfc_message_id: str | None = None  # the message the passage comes from
    attachment_order: int | None = None  # set when it comes from one of the message's files
    page: int | None = None


class Usage(Model):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None


class RunRecord(Model):
    """What a system returns for one question; the harness scores these."""

    question_id: QuestionId
    system: str
    arm: str
    retrieved: list[Retrieved] = Field(default_factory=list)
    answer_text: str = ""
    cited_ranks: list[int] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


# The tables of a corpus, in dependency order: file name -> record type.
TABLES: dict[str, type[Model]] = {
    "organisations": Organisation,
    "people": Person,
    "projects": Project,
    "facts": Fact,
    "fact_values": FactValue,
    "artifacts": Artifact,
    "versions": ArtifactVersion,
    "threads": Thread,
    "messages": Message,
    "occurrences": Occurrence,
    "spans": Span,
    "relations": Relation,
    "injections": Injection,
    "questions": Question,
}
