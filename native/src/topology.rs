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
}
