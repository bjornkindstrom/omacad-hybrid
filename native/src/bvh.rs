//! Immutable triangle BVH. Triangle and owner identities survive spatial reordering.
type Vec3 = [f64; 3];
fn sub(a: Vec3, b: Vec3) -> Vec3 {
    std::array::from_fn(|i| a[i] - b[i])
}
fn cross(a: Vec3, b: Vec3) -> Vec3 {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
fn dot(a: Vec3, b: Vec3) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

#[derive(Clone)]
pub struct Triangle {
    pub vertices: [Vec3; 3],
    pub owner: usize,
    pub index: usize,
}
impl Triangle {
    fn center(&self, axis: usize) -> f64 {
        self.vertices.iter().map(|v| v[axis] / 3.0).sum()
    }
    fn hit(&self, origin: Vec3, direction: Vec3, tolerance: f64) -> Option<f64> {
        let e1 = sub(self.vertices[1], self.vertices[0]);
        let e2 = sub(self.vertices[2], self.vertices[0]);
        let p = cross(direction, e2);
        let det = dot(e1, p);
        if det.abs() <= 1e-12 {
            return None;
        }
        let inv = 1.0 / det;
        let s = sub(origin, self.vertices[0]);
        let u = dot(s, p) * inv;
        let q = cross(s, e1);
        let w = dot(q, direction) * inv;
        let t = dot(e2, q) * inv;
        (u >= -tolerance && w >= -tolerance && u + w <= 1.0 + tolerance && t > 1e-6).then_some(t)
    }
}

struct Node {
    min: Vec3,
    max: Vec3,
    start: usize,
    end: usize,
    children: Option<(usize, usize)>,
}
impl Node {
    fn intersects(&self, origin: Vec3, direction: Vec3, tolerance: f64, best: f64) -> bool {
        let (mut near, mut far) = (0.0_f64, best);
        for axis in 0..3 {
            // Barycentric slack expands the triangle's bounds; padding is essential for
            // near-edge hits and coplanar bounds. Negative slack only shrinks triangles.
            let extent = self.max[axis] - self.min[axis];
            let rounding = self.max[axis].abs().max(self.min[axis].abs()).max(1.0) * 1e-12;
            let pad = 2.0 * tolerance.max(0.0) * extent + rounding;
            let lo = self.min[axis] - pad;
            let hi = self.max[axis] + pad;
            if direction[axis] == 0.0 {
                if origin[axis] < lo || origin[axis] > hi {
                    return false;
                }
            } else {
                let a = (lo - origin[axis]) / direction[axis];
                let b = (hi - origin[axis]) / direction[axis];
                near = near.max(a.min(b));
                far = far.min(a.max(b));
                if near > far {
                    return false;
                }
            }
        }
        true
    }
}

pub struct Bvh {
    triangles: Vec<Triangle>,
    nodes: Vec<Node>,
    pub faces: usize,
}
impl Bvh {
    pub fn new(triangles: Vec<Triangle>, faces: usize) -> Self {
        let mut tree = Self {
            triangles,
            nodes: Vec::new(),
            faces,
        };
        if !tree.triangles.is_empty() {
            tree.build(0, tree.triangles.len());
        }
        tree
    }
    fn build(&mut self, start: usize, end: usize) -> usize {
        let mut min = [f64::INFINITY; 3];
        let mut max = [f64::NEG_INFINITY; 3];
        let mut centers_min = min;
        let mut centers_max = max;
        for t in &self.triangles[start..end] {
            for axis in 0..3 {
                for v in &t.vertices {
                    min[axis] = min[axis].min(v[axis]);
                    max[axis] = max[axis].max(v[axis]);
                }
                let c = t.center(axis);
                centers_min[axis] = centers_min[axis].min(c);
                centers_max[axis] = centers_max[axis].max(c);
            }
        }
        let index = self.nodes.len();
        self.nodes.push(Node {
            min,
            max,
            start,
            end,
            children: None,
        });
        if end - start > 8 {
            let axis = (0..3)
                .max_by(|&a, &b| {
                    (centers_max[a] - centers_min[a]).total_cmp(&(centers_max[b] - centers_min[b]))
                })
                .unwrap();
            if centers_max[axis] > centers_min[axis] {
                let mid = (start + end) / 2;
                self.triangles[start..end].select_nth_unstable_by(mid - start, |a, b| {
                    a.center(axis)
                        .total_cmp(&b.center(axis))
                        .then(a.index.cmp(&b.index))
                });
                let left = self.build(start, mid);
                let right = self.build(mid, end);
                self.nodes[index].children = Some((left, right));
            }
        }
        index
    }
    pub fn face_hits(&self, origin: Vec3, direction: Vec3, tolerance: f64) -> Vec<f64> {
        let mut hits = vec![f64::INFINITY; self.faces];
        self.visit(
            origin,
            direction,
            tolerance,
            || f64::INFINITY,
            |tri, t| {
                hits[tri.owner] = hits[tri.owner].min(t);
            },
        );
        hits
    }
    pub fn nearest(&self, origin: Vec3, direction: Vec3, tolerance: f64) -> Option<(f64, usize)> {
        // Cell lets traversal tighten the bound as a nearer triangle is found.
        let distance = std::cell::Cell::new(f64::INFINITY);
        let mut index = usize::MAX;
        self.visit(
            origin,
            direction,
            tolerance,
            || distance.get(),
            |tri, t| {
                if t < distance.get() || (t == distance.get() && tri.index < index) {
                    distance.set(t);
                    index = tri.index;
                }
            },
        );
        (index != usize::MAX).then_some((distance.get(), index))
    }
    fn visit(
        &self,
        origin: Vec3,
        direction: Vec3,
        tolerance: f64,
        bound: impl Fn() -> f64,
        mut hit: impl FnMut(&Triangle, f64),
    ) {
        if self.nodes.is_empty() {
            return;
        }
        let mut stack = vec![0];
        while let Some(index) = stack.pop() {
            let node = &self.nodes[index];
            if !node.intersects(origin, direction, tolerance, bound()) {
                continue;
            }
            if let Some((left, right)) = node.children {
                stack.push(right);
                stack.push(left);
            } else {
                for tri in &self.triangles[node.start..node.end] {
                    if let Some(t) = tri.hit(origin, direction, tolerance) {
                        hit(tri, t);
                    }
                }
            }
        }
    }
    pub fn triangle_count(&self) -> usize {
        self.triangles.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn triangle(index: usize, z: f64) -> Triangle {
        Triangle {
            vertices: [[0.0, 0.0, z], [1.0, 0.0, z], [0.0, 1.0, z]],
            owner: index,
            index,
        }
    }
    #[test]
    fn all_face_hits_are_retained_and_nearest_keeps_original_identity() {
        let tree = Bvh::new((0..40).rev().map(|i| triangle(i, i as f64)).collect(), 40);
        let hits = tree.face_hits([0.2, 0.2, 50.0], [0.0, 0.0, -1.0], 1e-9);
        for (i, t) in hits.iter().enumerate() {
            assert_eq!(*t, 50.0 - i as f64);
        }
        assert_eq!(
            tree.nearest([0.2, 0.2, 50.0], [0.0, 0.0, -1.0], 1e-9),
            Some((11.0, 39))
        );
    }
    #[test]
    fn empty_parallel_and_behind_rays_miss() {
        assert!(
            Bvh::new(vec![], 0)
                .nearest([0.0; 3], [0.0; 3], 1e-9)
                .is_none()
        );
        let b = Bvh::new(vec![triangle(0, 0.0)], 1);
        assert!(b.nearest([0.2, 0.2, 1.0], [1.0, 0.0, 0.0], 1e-9).is_none());
        assert!(b.nearest([0.2, 0.2, 1.0], [0.0, 0.0, 1.0], 1e-9).is_none());
        assert!(b.nearest([0.2, 0.2, 1.0], [0.0; 3], 1e-9).is_none());
    }
    #[test]
    fn tolerance_extends_bounds_and_ties_choose_first_original_triangle() {
        let b = Bvh::new(vec![triangle(0, 0.0), triangle(1, 0.0)], 2);
        assert_eq!(
            b.nearest([-5e-5, 0.2, 1.0], [0.0, 0.0, -1.0], 1e-4),
            Some((1.0, 0))
        );
        assert!(
            b.nearest([-5e-5, 0.2, 1.0], [0.0, 0.0, -1.0], 1e-9)
                .is_none()
        );
    }
}
