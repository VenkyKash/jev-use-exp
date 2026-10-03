"""Snapshot-local hierarchy inspection. Navigation here never touches the UI."""
from dataclasses import replace
from collections import defaultdict

from core import Candidate


class HierarchyView:
    def __init__(self, observation, page_size=16):
        self.observation = observation
        self.nodes = {e.index: e for e in observation.elements}
        self.children = defaultdict(list)
        for e in observation.elements:
            self.children[e.parent if e.parent in self.nodes else None].append(e.index)
        self.parent, self.offset = None, 0
        self.page_size = page_size
        # Stable within this snapshot, independent of branch navigation. This is
        # context only: it neither creates candidates nor carries action tokens.
        roots = self.children[None]
        overview_ids = list(roots[:page_size])
        for root in roots[:page_size]:
            overview_ids.extend(self.children[root][:page_size])
        self.root_context = dict(
            snapshot_id=observation.id,
            controls=[dict(id=i, role=self.nodes[i].role, label=self.nodes[i].label,
                           value=self.nodes[i].value, parent=self.nodes[i].parent,
                           child_count=len(self.children[i])) for i in overview_ids],
            roots_not_shown=max(0, len(roots)-page_size),
            children_not_shown={str(i): len(self.children[i])-page_size
                                for i in roots[:page_size] if len(self.children[i]) > page_size},
            scope="Root overview and first child pages, retained during inspection. Additional controls remain reachable via hierarchy pages.")

    def project(self):
        siblings = self.children[self.parent]
        visible = siblings[self.offset:self.offset+self.page_size]
        ids = ([self.parent] if self.parent is not None else []) + visible
        trail, node = [], self.parent
        while node is not None:
            e = self.nodes[node]
            trail.append(dict(id=node, role=e.role, label=e.label[:120]))
            node = e.parent if e.parent in self.nodes else None
        inspection = dict(kind="local_hierarchy", snapshot_id=self.observation.id,
            breadcrumb=list(reversed(trail)), parent=self.parent,
            sibling_count=len(siblings), range_start=self.offset,
            range_end=self.offset+len(visible), total_controls=len(self.nodes),
            branches=[dict(id=i, child_count=len(self.children[i])) for i in visible],
            semantics="Only this branch/page is exposed. Expand shows children, not a click. Other controls remain accessible via parent, root and sibling pages. Missing parents are shown at root; no semantic groups are invented.")
        return replace(self.observation, elements=tuple(self.nodes[i] for i in ids),
                       complete=False, readback_text="", menu_paths=(), inspection=inspection,
                       root_context=self.root_context)

    def choices(self):
        siblings = self.children[self.parent]
        choices = []
        for i in siblings[self.offset:self.offset+self.page_size]:
            if self.children[i]:
                e = self.nodes[i]
                choices.append(Candidate(f"tree-expand-{i}",
                    f"Inspect children of {e.role} {e.label[:120]!r}, element {i}; {len(self.children[i])} children. Local read only, no click.", None, {}))
        if self.parent is not None:
            choices.extend([Candidate("tree-parent", "Inspect parent branch; no UI action.", None, {}),
                            Candidate("tree-root", "Return to full hierarchy index at root; no UI action.", None, {})])
        if self.offset:
            choices.append(Candidate("tree-previous", "Inspect previous sibling index range; no UI action.", None, {}))
        if self.offset+self.page_size < len(siblings):
            choices.append(Candidate("tree-next", f"Inspect next sibling index range, starting at {self.offset+self.page_size}; no UI action.", None, {}))
        return choices

    def navigate(self, selected, snapshot_id):
        if snapshot_id != self.observation.id:
            raise ValueError("stale hierarchy snapshot")
        if selected not in {c.id for c in self.choices()}:
            raise ValueError("unknown hierarchy choice")
        if selected.startswith("tree-expand-"):
            self.parent, self.offset = int(selected.removeprefix("tree-expand-")), 0
        elif selected == "tree-next":
            self.offset += self.page_size
        elif selected == "tree-previous":
            self.offset -= self.page_size
        elif selected == "tree-root":
            self.parent, self.offset = None, 0
        else:
            child = self.parent
            parent = self.nodes[child].parent
            self.parent = parent if parent in self.nodes else None
            self.offset = self.children[self.parent].index(child)//self.page_size*self.page_size
