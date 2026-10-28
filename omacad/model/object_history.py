"""Persistent ownership and dependency links, independent of rendered bodies.

The ordered feature list remains the compatibility execution schedule. Object
histories contain stable IDs, never indexes into that schedule.
"""
from dataclasses import dataclass, field
import copy


@dataclass
class ModelObject:
    object_id: str
    name: str
    feature_ids: list = field(default_factory=list)
    body_ids: list = field(default_factory=list)
    origin_feature_id: str | None = None
    parent_id: str | None = None          # the object a Combine used this one up in
    consumed_by: str | None = None        # that Combine's feature id


class ObjectHistory:
    def __init__(self):
        self.owners = {}
        self.names = {}
        self.outputs = {}
        self.dependencies = {}
        self.markers = {}
        self.active_id = None
        self.objects = {}
        self.insert_after = None
        self.target_object_id = None

    def to_dict(self):
        return copy.deepcopy(dict(owners=self.owners, names=self.names,
                                  outputs=self.outputs, dependencies=self.dependencies,
                                  markers=self.markers, active_id=self.active_id))

    def load(self, data):
        for key in ('owners', 'names', 'outputs', 'dependencies', 'markers'):
            setattr(self, key, copy.deepcopy(data.get(key, {})))
        self.active_id = data.get('active_id')
        self.objects = {}
        self.insert_after = None
        self.target_object_id = None

    @staticmethod
    def sketch_inputs(feature):
        refs = [getattr(feature, 'sketch_id', None)]
        for key in ('extra_refs', 'holes', 'extra_profiles', 'sections'):
            for value in getattr(feature, key, None) or []:
                if isinstance(value, (list, tuple)) and value:
                    refs.append(value[0])
        path = getattr(feature, 'path', None)
        if isinstance(path, (list, tuple)) and path:
            refs.append(path[0])
        return [r for r in refs if isinstance(r, str)]

    @staticmethod
    def body_inputs(feature):
        refs = [getattr(feature, key, None) for key in ('target_body_id', 'tool_body_id')]
        for key in ('edges', 'faces', 'points'):
            for value in getattr(feature, key, None) or []:
                if isinstance(value, dict):
                    refs.append(value.get('body_id'))
                elif isinstance(value, (list, tuple)) and value and isinstance(value[0], str):
                    refs.append(value[0])
        if feature.feature_type == 'sketch':
            refs.append(getattr(feature.sketch, 'parent_body_id', None))
        for key in ('from_point', 'to_point'):
            ref = getattr(feature, key, None)
            if isinstance(ref, dict):
                refs.append(ref.get('body'))
        refs += list(getattr(feature, 'target_body_ids', None) or [])
        return list(dict.fromkeys(r for r in refs if isinstance(r, str)))

    def sync(self, doc):
        """Reconcile stored identities with features and observed replay outputs.

        Old implicit multi-body operations are discovered from replay footprints;
        ownership is retained when a feature is later suppressed or fails.
        """
        features = doc.timeline.features
        valid = {f.feature_id for f in features}
        self.owners = {k: v for k, v in self.owners.items() if k in valid}
        self.outputs = {k: v for k, v in self.outputs.items() if k in valid}
        objects, bodies, sketches, last_body = {}, {}, {}, {}
        states = getattr(doc, 'step_states', {})
        state_ids = getattr(doc.timeline, '_step_feature_ids', ())
        for index, feat in enumerate(features):
            fid = feat.feature_id
            refs = self.body_inputs(feat)
            sk_refs = self.sketch_inputs(feat)
            before, after = states.get(index), states.get(index + 1)
            if index >= len(state_ids) or state_ids[index] != fid:
                before, after = None, None
            touched = []
            if before is not None and after is not None and not feat.suppressed and not feat.error:
                touched = [bid for bid in dict.fromkeys([*before, *after])
                           if before.get(bid) is not after.get(bid)]
                if touched:
                    self.outputs[fid] = touched
            created = getattr(feat, 'created_body_id', f'body_{fid}')
            outputs = self.outputs.get(fid, [])
            if not outputs and getattr(feat, '_last_body_outputs', None):
                outputs = self.outputs[fid] = list(feat._last_body_outputs)
            creates = (feat.feature_type in ('box', 'cylinder', 'cone', 'prism', 'sphere', 'import_mesh', 'branch', 'split_body')
                       or getattr(feat, 'operation', None) == 'new_body'
                       or (feat.feature_type == 'move' and feat.copy_body))
            if creates or created in doc.bodies or (after is not None and created in after):
                outputs = list(dict.fromkeys([*outputs, created]))
                self.outputs[fid] = outputs
            candidates = [bodies[b] for b in refs + outputs if b in bodies]
            # A new-body feature continues its source sketch's object only once.
            candidates += [self.owners[sketches[s]] for s in sk_refs if s in sketches
                           and not objects[self.owners[sketches[s]]].body_ids]
            source_ids = getattr(feat, 'source_ids', None) or []
            candidates += [self.owners[s] for s in source_ids if s in self.owners]
            if feat.feature_type == 'branch' or (feat.feature_type == 'move' and feat.copy_body):
                candidates = []
            owner = self.owners.setdefault(fid, candidates[0] if candidates else 'object_' + fid)
            # Legacy implicit operations can only acquire their owner after replay
            # reveals which bodies they actually changed.
            if candidates and owner == 'object_' + fid and not creates and feat.feature_type != 'sketch':
                owner = self.owners[fid] = candidates[0]
            obj = objects.setdefault(owner, ModelObject(owner, self.names.get(owner, feat.name)))
            obj.feature_ids.append(fid)
            deps = [last_body[b] for b in refs + outputs if b in last_body]
            path = getattr(feat, 'path', None)
            searches_geometry = (isinstance(path, (tuple, list)) and path and path[0] == '@edges')
            searches_geometry = searches_geometry or (feat.feature_type == 'sketch' and bool(feat.sketch.reference_segments))
            if searches_geometry:
                # Existing sketch projections and edge paths search earlier scene
                # geometry. Keep conservative read dependencies rather than guess
                # which references may be safely detached during local rollback.
                # Every body made before the step, from the history itself: replay-time inputs would differ between
                # a freshly added step and the same step after undo/reload.
                deps += list(last_body.values())
            deps += [sketches[s] for s in sk_refs if s in sketches]
            deps += [s for s in source_ids if s in valid]
            source = getattr(feat, 'source_feature_id', None)
            if source in valid:
                deps.append(source)
            deps += [s for s in self.dependencies.get(fid, []) if s in valid]
            if len(obj.feature_ids) > 1:
                deps.append(obj.feature_ids[-2])
            self.dependencies[fid] = list(dict.fromkeys(d for d in deps if d != fid))
            if feat.feature_type == 'sketch':
                sketches[feat.sketch.sketch_id] = fid
            tool = bodies.get(getattr(feat, 'tool_body_id', None))
            if (feat.feature_type == 'combine' and not feat.keep_tool and not feat.suppressed
                    and tool in objects and tool != owner and not self._is_ancestor(objects, tool, owner)):
                # The tool body is gone into the target: its object becomes a branch of the target's object.
                objects[tool].parent_id, objects[tool].consumed_by = owner, fid
            for bid in outputs:
                if feat.feature_type == 'split_body' and bid == created:
                    split_owner = 'object_' + fid + '_split'
                    bodies[bid] = split_owner
                    objects.setdefault(split_owner, ModelObject(split_owner,
                        self.names.get(split_owner, feat.new_body_name or feat.name + ' result'),
                        origin_feature_id=fid))
                bodies.setdefault(bid, owner)
                last_body[bid] = fid
                target = objects.get(bodies[bid], obj)
                if bid not in target.body_ids:
                    target.body_ids.append(bid)
        self.objects = objects
        self.names = {k: v for k, v in self.names.items() if k in objects}
        self.dependencies = {k: v for k, v in self.dependencies.items() if k in valid}
        self.markers = {k: v for k, v in self.markers.items()
                        if k in objects and (v is None or v in objects[k].feature_ids)}
        if self.active_id not in objects:
            self.active_id = next(reversed(objects), None) if objects else None
        return objects

    @staticmethod
    def _is_ancestor(objects, oid, of):
        while of is not None:
            if of == oid:
                return True
            of = objects[of].parent_id if of in objects else None
        return False

    def children(self, parent_id):
        """Objects used up by a Combine of `parent_id`, keyed by that Combine's feature id."""
        found = {}
        for oid, obj in self.objects.items():
            if obj.parent_id == parent_id:
                found.setdefault(obj.consumed_by, []).append(oid)
        return found

    def excluded(self):
        """Features beyond local cursors and their transitive dependents."""
        excluded = set()
        for oid, marker in self.markers.items():
            obj = self.objects.get(oid)
            if obj is None:
                continue
            pos = obj.feature_ids.index(marker) + 1 if marker in obj.feature_ids else 0
            excluded.update(obj.feature_ids[pos:])
        changed = True
        while changed:
            changed = False
            for fid, deps in self.dependencies.items():
                if fid not in excluded and any(d in excluded for d in deps):
                    excluded.add(fid)
                    changed = True
        return excluded

    def index(self, doc, feature_id):
        return next((i for i, f in enumerate(doc.timeline.features) if f.feature_id == feature_id), None)
