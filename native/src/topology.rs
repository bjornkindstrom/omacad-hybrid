//! Exact-order union-find passes used by Omacad's existing topology/shading rules.
use pyo3::{exceptions::PyValueError, prelude::*, types::PyBytes};
use std::collections::HashMap;

fn root(parent: &mut [usize], mut i: usize) -> usize {
    while parent[i] != i {
        parent[i] = parent[parent[i]];
        i = parent[i];
    }
    i
}
fn pairs(bytes: &[u8], count: usize) -> PyResult<Vec<[usize; 2]>> {
    if bytes.len() % 16 != 0 {
        return Err(PyValueError::new_err("adjacency must contain uint64 pairs"));
    }
    bytes
        .chunks_exact(16)
        .map(|b| {
            let a = usize::try_from(u64::from_le_bytes(b[..8].try_into().unwrap()))
                .map_err(|_| PyValueError::new_err("index too large"))?;
            let c = usize::try_from(u64::from_le_bytes(b[8..].try_into().unwrap()))
                .map_err(|_| PyValueError::new_err("index too large"))?;
            if a >= count || c >= count {
                return Err(PyValueError::new_err("adjacency index outside face array"));
            }
            Ok([a, c])
        })
        .collect()
}
fn floats<const N: usize>(bytes: &[u8]) -> PyResult<Vec<[f64; N]>> {
    if bytes.len() % (N * 8) != 0 {
        return Err(PyValueError::new_err("incorrect float64 buffer size"));
    }
    bytes
        .chunks_exact(N * 8)
        .map(|chunk| {
            let array = std::array::from_fn(|i| {
                f64::from_le_bytes(chunk[i * 8..i * 8 + 8].try_into().unwrap())
            });
            if array.iter().any(|v| !v.is_finite()) {
                return Err(PyValueError::new_err("non-finite topology data"));
            }
            Ok(array)
        })
        .collect()
}
fn dot(a: &[f64], b: &[f64]) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

#[pyfunction]
pub fn flat_patch_mask<'py>(
    py: Python<'py>,
    count: usize,
    coplanar_pairs: &[u8],
    sharp_pairs: &[u8],
    directions: &[u8],
    single_precision: bool,
) -> PyResult<Bound<'py, PyBytes>> {
    let coplanar = pairs(coplanar_pairs, count)?;
    let sharp = pairs(sharp_pairs, count)?;
    let directions = floats::<3>(directions)?;
    if sharp.len() != directions.len() {
        return Err(PyValueError::new_err("sharp-edge direction count mismatch"));
    }
    let mask = py.detach(move || {
        let mut parent: Vec<_> = (0..count).collect();
        // Deliberately preserve Python's right-root union rule, rather than union by rank.
        for [a, b] in coplanar {
            let ra = root(&mut parent, a);
            let rb = root(&mut parent, b);
            parent[ra] = rb;
        }
        let mut first: HashMap<usize, [f64; 3]> = HashMap::new();
        let mut flat = vec![false; count];
        for ([a, b], direction) in sharp.into_iter().zip(directions) {
            for face in [a, b] {
                let patch = root(&mut parent, face);
                if let Some(f) = first.get(&patch) {
                    let sharp = if single_precision {
                        let f = f.map(|v| v as f32);
                        let d = direction.map(|v| v as f32);
                        let x = f[1] * d[2] - f[2] * d[1];
                        let y = f[2] * d[0] - f[0] * d[2];
                        let z = f[0] * d[1] - f[1] * d[0];
                        x * x + y * y + z * z > 0.01_f32
                    } else {
                        let x = f[1] * direction[2] - f[2] * direction[1];
                        let y = f[2] * direction[0] - f[0] * direction[2];
                        let z = f[0] * direction[1] - f[1] * direction[0];
                        x * x + y * y + z * z > 0.01
                    };
                    if sharp {
                        flat[patch] = true;
                    }
                } else {
                    first.insert(patch, direction);
                }
            }
        }
        (0..count)
            .map(|i| u8::from(flat[root(&mut parent, i)]))
            .collect::<Vec<_>>()
    });
    Ok(PyBytes::new(py, &mask))
}

#[pyfunction]
pub fn coplanar_roots<'py>(
    py: Python<'py>,
    triangles: &[u8],
    normals: &[u8],
    areas: &[u8],
    adjacency: &[u8],
    tolerance: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    let triangles = floats::<9>(triangles)?;
    let normals = floats::<3>(normals)?;
    let areas = floats::<1>(areas)?;
    let count = triangles.len();
    if normals.len() != count || areas.len() != count || !tolerance.is_finite() || tolerance < 0.0 {
        return Err(PyValueError::new_err(
            "topology lengths/tolerance do not match",
        ));
    }
    let adjacent = pairs(adjacency, count)?;
    let bytes = py.detach(move || {
        let mut parent: Vec<_> = (0..count).collect();
        for [a, b] in adjacent {
            let n = &normals[a];
            let d = dot(n, &normals[b]);
            let pa = &triangles[a][..3];
            let pb = &triangles[b][..3];
            // Same ordered expressions and tolerance rules as faces_topology._coplanar.
            let off = (dot(n, pa) - dot(n, pb)).abs();
            let mut coplanar = d > 1.0 - 1e-9 && off < tolerance;
            if !coplanar && d > 1.0 - 1e-7 {
                let mut max_off = 0.0_f64;
                for corner in triangles[b].chunks_exact(3) {
                    let delta = [corner[0] - pa[0], corner[1] - pa[1], corner[2] - pa[2]];
                    max_off = max_off.max(dot(&delta, n).abs());
                }
                coplanar = max_off < tolerance;
            }
            if !coplanar {
                coplanar = areas[a][0].min(areas[b][0]) < 0.01 && d > 1.0 - 1e-4 && off < 1e-3;
            }
            if coplanar {
                let ra = root(&mut parent, a);
                let rb = root(&mut parent, b);
                if ra != rb {
                    parent[rb] = ra;
                }
            }
        }
        (0..count)
            .flat_map(|i| (root(&mut parent, i) as u64).to_le_bytes())
            .collect::<Vec<_>>()
    });
    Ok(PyBytes::new(py, &bytes))
}

#[pyfunction]
pub fn snap_and_clean_segments<'py>(
    py: Python<'py>,
    vertices: &[u8],
    segments: &[u8],
    snap_tol: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    let vertices = floats::<3>(vertices)?;
    let count = vertices.len();
    if segments.len() % 16 != 0 || !snap_tol.is_finite() || snap_tol < 0.0 {
        return Err(PyValueError::new_err(
            "invalid segment buffer or snap tolerance",
        ));
    }
    let seg_pairs: Vec<[usize; 2]> = segments
        .chunks_exact(16)
        .map(|b| {
            let s0 = usize::try_from(u64::from_le_bytes(b[..8].try_into().unwrap()))
                .map_err(|_| PyValueError::new_err("index too large"))?;
            let s1 = usize::try_from(u64::from_le_bytes(b[8..].try_into().unwrap()))
                .map_err(|_| PyValueError::new_err("index too large"))?;
            if s0 >= count || s1 >= count {
                return Err(PyValueError::new_err("segment index outside vertex array"));
            }
            Ok([s0, s1])
        })
        .collect::<PyResult<Vec<_>>>()?;

    let bytes = py.detach(move || {
        let snap_tol_sq = snap_tol * snap_tol;
        let mut representatives: Vec<usize> = Vec::new();
        let mut memo: HashMap<usize, usize> = HashMap::new();

        let mut snap_vertex = |idx: usize| -> usize {
            if let Some(&rep) = memo.get(&idx) {
                return rep;
            }
            let p = &vertices[idx];
            for &cand in &representatives {
                let cp = &vertices[cand];
                let dx = cp[0] - p[0];
                let dy = cp[1] - p[1];
                let dz = cp[2] - p[2];
                if dx * dx + dy * dy + dz * dz <= snap_tol_sq {
                    memo.insert(idx, cand);
                    return cand;
                }
            }
            representatives.push(idx);
            memo.insert(idx, idx);
            idx
        };

        let mut seen = std::collections::HashSet::new();
        let mut cleaned_indices = Vec::new();

        for (i, [s0, s1]) in seg_pairs.iter().enumerate() {
            let a = snap_vertex(*s0);
            let b = snap_vertex(*s1);
            if a == b {
                continue;
            }
            let key = (a.min(b), a.max(b));
            if seen.insert(key) {
                cleaned_indices.push((i as u64, a as u64, b as u64));
            }
        }

        // Return (original_idx, snapped_a, snapped_b) as uint64 triples
        let mut out = Vec::with_capacity(cleaned_indices.len() * 24);
        for (orig, a, b) in cleaned_indices {
            out.extend_from_slice(&orig.to_le_bytes());
            out.extend_from_slice(&a.to_le_bytes());
            out.extend_from_slice(&b.to_le_bytes());
        }
        out
    });
    Ok(PyBytes::new(py, &bytes))
}

fn triples(bytes: &[u8], count: usize) -> PyResult<Vec<[usize; 3]>> {
    if bytes.len() % 24 != 0 {
        return Err(PyValueError::new_err("triangles must contain uint64 triples"));
    }
    bytes
        .chunks_exact(24)
        .map(|b| {
            let mut out = [0usize; 3];
            for (dst, src) in out.iter_mut().zip(b.chunks_exact(8)) {
                *dst = usize::try_from(u64::from_le_bytes(src.try_into().unwrap()))
                    .map_err(|_| PyValueError::new_err("index too large"))?;
                if *dst >= count {
                    return Err(PyValueError::new_err("triangle index outside vertex array"));
                }
            }
            Ok(out)
        })
        .collect()
}

/// Eigenvalues and eigenvectors (columns) of a symmetric 3x3 matrix, by cyclic Jacobi rotations.
fn symmetric_eigen(mut a: [[f64; 3]; 3]) -> ([f64; 3], [[f64; 3]; 3]) {
    let mut vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
    for _ in 0..32 {
        if a[0][1].abs() + a[0][2].abs() + a[1][2].abs() == 0.0 {
            break;
        }
        for (p, q) in [(0, 1), (0, 2), (1, 2)] {
            if a[p][q] == 0.0 {
                continue;
            }
            let theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
            let t = theta.signum() / (theta.abs() + (theta * theta + 1.0).sqrt());
            let c = 1.0 / (t * t + 1.0).sqrt();
            let s = t * c;
            for row in a.iter_mut() {
                let (x, y) = (row[p], row[q]);
                row[p] = c * x - s * y;
                row[q] = s * x + c * y;
            }
            for k in 0..3 {
                let (x, y) = (a[p][k], a[q][k]);
                a[p][k] = c * x - s * y;
                a[q][k] = s * x + c * y;
            }
            for row in vectors.iter_mut() {
                let (x, y) = (row[p], row[q]);
                row[p] = c * x - s * y;
                row[q] = s * x + c * y;
            }
        }
    }
    ([a[0][0], a[1][1], a[2][2]], vectors)
}

/// faces_topology._group_min_width for a group of several triangles, given its distinct vertices: the narrower extent
/// along the two main axes of the points.
fn group_min_width(points: &[[f64; 3]]) -> f64 {
    if points.len() < 3 {
        return 0.0;
    }
    let mut mean = [0.0; 3];
    for p in points {
        for k in 0..3 {
            mean[k] += p[k];
        }
    }
    mean = mean.map(|m| m / points.len() as f64);
    let mut scatter = [[0.0; 3]; 3];
    for p in points {
        let c = [p[0] - mean[0], p[1] - mean[1], p[2] - mean[2]];
        for i in 0..3 {
            for j in 0..3 {
                scatter[i][j] += c[i] * c[j];
            }
        }
    }
    let (values, vectors) = symmetric_eigen(scatter);
    let mut order = [0, 1, 2];
    order.sort_by(|&a, &b| values[b].total_cmp(&values[a]));
    let mut narrowest = f64::INFINITY;
    for &axis in &order[..2] {
        let (mut low, mut high) = (f64::INFINITY, f64::NEG_INFINITY);
        for p in points {
            let along = (p[0] - mean[0]) * vectors[0][axis]
                + (p[1] - mean[1]) * vectors[1][axis]
                + (p[2] - mean[2]) * vectors[2][axis];
            low = low.min(along);
            high = high.max(along);
        }
        narrowest = narrowest.min(high - low);
    }
    narrowest
}

/// faces_topology._curved_roots' width_across: the extent of `points` across the seam with a neighbour of normal `nb`.
fn width_across(points: &[[f64; 3]], n: &[f64; 3], nb: &[f64; 3]) -> f64 {
    let along = dot(nb, n);
    let axis = [nb[0] - along * n[0], nb[1] - along * n[1], nb[2] - along * n[2]];
    let length = dot(&axis, &axis).sqrt();
    if length < 1e-6 {
        return 0.0; // coplanar patches separated by a sliver do not establish curvature
    }
    let axis = axis.map(|a| a / length);
    let (mut low, mut high) = (f64::INFINITY, f64::NEG_INFINITY);
    for p in points {
        let d = dot(p, &axis);
        low = low.min(d);
        high = high.max(d);
    }
    high - low
}

/// faces_topology._sliver_roots and _curved_roots at once. Returns one byte per triangle index, read for the indices
/// that are group roots: bit 0 = sliver, bit 1 = curved. Python holds the thresholds, and stays the reference path.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn classify_face_groups<'py>(
    py: Python<'py>,
    vertices: &[u8],
    triangles: &[u8],
    normals: &[u8],
    areas: &[u8],
    roots: &[u8],
    adjacency: &[u8],
    angles: &[u8],
    sliver_area: f64,
    sliver_min_width: f64,
    shallow_angle: f64,
    shallow_dot: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    let vertices = floats::<3>(vertices)?;
    let triangles = triples(triangles, vertices.len())?;
    let normals = floats::<3>(normals)?;
    let areas = floats::<1>(areas)?;
    let count = triangles.len();
    let adjacent = pairs(adjacency, count)?;
    let angles = floats::<1>(angles)?;
    if normals.len() != count
        || areas.len() != count
        || roots.len() != count * 8
        || angles.len() != adjacent.len()
    {
        return Err(PyValueError::new_err("topology lengths do not match"));
    }
    let roots = roots
        .chunks_exact(8)
        .map(|b| {
            usize::try_from(u64::from_le_bytes(b.try_into().unwrap()))
                .ok()
                .filter(|&r| r < count)
                .ok_or_else(|| PyValueError::new_err("root outside face array"))
        })
        .collect::<PyResult<Vec<_>>>()?;

    let bytes = py.detach(move || {
        let mut members: Vec<Vec<u32>> = vec![Vec::new(); count];
        for (tri, &r) in roots.iter().enumerate() {
            members[r].push(tri as u32);
        }
        // the distinct corners of each group, as np.unique(f[ids]) gives them
        let points: Vec<Vec<[f64; 3]>> = members
            .iter()
            .map(|ids| {
                let mut corners: Vec<usize> =
                    ids.iter().flat_map(|&t| triangles[t as usize]).collect();
                corners.sort_unstable();
                corners.dedup();
                corners.into_iter().map(|c| vertices[c]).collect()
            })
            .collect();

        let mut sliver = vec![false; count];
        for (r, ids) in members.iter().enumerate() {
            sliver[r] = match ids.as_slice() {
                [] => false,
                [t] => {
                    let area = areas[*t as usize][0];
                    let [a, b, c] = triangles[*t as usize].map(|i| vertices[i]);
                    let side = |p: [f64; 3], q: [f64; 3]| {
                        let d = [q[0] - p[0], q[1] - p[1], q[2] - p[2]];
                        dot(&d, &d).sqrt()
                    };
                    let longest = side(a, b).max(side(b, c)).max(side(c, a)).max(1e-12);
                    area < sliver_area || 2.0 * area / longest < sliver_min_width
                }
                _ => {
                    ids.iter().map(|&t| areas[t as usize][0]).sum::<f64>() < sliver_area
                        || group_min_width(&points[r]) < sliver_min_width
                }
            };
        }

        let mut shallow: Vec<Vec<u32>> = vec![Vec::new(); count];
        let mut touching: Vec<Vec<u32>> = vec![Vec::new(); count];
        for ([a, b], angle) in adjacent.iter().zip(&angles) {
            let (ra, rb) = (roots[*a], roots[*b]);
            if ra == rb {
                continue;
            }
            touching[ra].push(rb as u32);
            touching[rb].push(ra as u32);
            if angle[0] < shallow_angle {
                shallow[ra].push(rb as u32);
                shallow[rb].push(ra as u32);
            }
        }
        for list in touching.iter_mut() {
            list.sort_unstable();
            list.dedup();
        }
        let normal_of = |r: usize| &normals[members[r][0] as usize];

        // slivers often come in chains: look through whole clusters of them
        let mut cluster: Vec<usize> = (0..count).collect();
        for r in (0..count).filter(|&r| sliver[r]) {
            for &n in &touching[r] {
                if sliver[n as usize] {
                    let (ra, rb) = (root(&mut cluster, n as usize), root(&mut cluster, r));
                    if ra != rb {
                        cluster[ra] = rb;
                    }
                }
            }
        }
        let mut real: HashMap<usize, Vec<u32>> = HashMap::new();
        for r in (0..count).filter(|&r| sliver[r]) {
            let c = root(&mut cluster, r);
            real.entry(c)
                .or_default()
                .extend(touching[r].iter().filter(|&&n| !sliver[n as usize]));
        }
        for list in real.values_mut() {
            list.sort_unstable();
            list.dedup();
            for &x in list.iter() {
                for &y in list.iter() {
                    if x != y && dot(normal_of(x as usize), normal_of(y as usize)) > shallow_dot {
                        shallow[x as usize].push(y);
                    }
                }
            }
        }

        let mut classes: Vec<u8> = sliver.iter().map(|&s| u8::from(s)).collect();
        for r in 0..count {
            if sliver[r] || shallow[r].is_empty() {
                continue;
            }
            shallow[r].sort_unstable();
            shallow[r].dedup();
            let mut similar = 0;
            for &n in &shallow[r] {
                let n = n as usize;
                if sliver[n] {
                    continue;
                }
                let wide = width_across(&points[r], normal_of(r), normal_of(n));
                if wide > 0.0
                    && width_across(&points[n], normal_of(n), normal_of(r)) >= wide * 0.25
                {
                    similar += 1;
                    if similar >= 2 {
                        classes[r] |= 2;
                        break;
                    }
                }
            }
        }
        classes
    });
    Ok(PyBytes::new(py, &bytes))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn union_order_preserves_root_identity() {
        let mut parents: Vec<_> = (0..5).collect();
        for (a, b) in [(0, 1), (2, 3), (1, 3)] {
            let a = root(&mut parents, a);
            let b = root(&mut parents, b);
            parents[b] = a;
        }
        assert_eq!(
            (0..5).map(|i| root(&mut parents, i)).collect::<Vec<_>>(),
            vec![0, 0, 0, 0, 4]
        );
    }

    #[test]
    fn snap_and_clean_preserves_topology() {
        let vertices = vec![
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.000000001, 0.0, 0.0], // snaps to 1
            [2.0, 0.0, 0.0],
        ];
        let snap_tol_sq = 1e-6 * 1e-6;
        let mut representatives: Vec<usize> = Vec::new();
        let mut memo: HashMap<usize, usize> = HashMap::new();
        let mut snap_vertex = |idx: usize| -> usize {
            if let Some(&rep) = memo.get(&idx) {
                return rep;
            }
            let p = &vertices[idx];
            for &cand in &representatives {
                let cp = &vertices[cand];
                let dx = cp[0] - p[0];
                let dy = cp[1] - p[1];
                let dz = cp[2] - p[2];
                if dx * dx + dy * dy + dz * dz <= snap_tol_sq {
                    memo.insert(idx, cand);
                    return cand;
                }
            }
            representatives.push(idx);
            memo.insert(idx, idx);
            idx
        };
        assert_eq!(snap_vertex(0), 0);
        assert_eq!(snap_vertex(1), 1);
        assert_eq!(snap_vertex(2), 1);
        assert_eq!(snap_vertex(3), 3);
    }

    #[test]
    fn eigenvectors_of_a_rotated_strip_give_its_two_extents() {
        // a 10 x 0.5 strip turned 30 degrees about z, in the plane z = 3
        let (c, s) = (30.0_f64.to_radians().cos(), 30.0_f64.to_radians().sin());
        let strip: Vec<[f64; 3]> = [(0.0, 0.0), (10.0, 0.0), (10.0, 0.5), (0.0, 0.5)]
            .iter()
            .map(|&(x, y)| [c * x - s * y, s * x + c * y, 3.0])
            .collect();
        assert!((group_min_width(&strip) - 0.5).abs() < 1e-9);
    }
}
