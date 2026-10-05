//! Pure-Rust linear algebra for the PLDA setup (nalgebra-backed).
//!
//! Replaces ndarray-linalg/LAPACK on purpose: ndarray-linalg flips ndarray's
//! `blas` feature on, which unifies into every binary of this crate and breaks
//! linking. The two operations needed (matrix inverse and the generalized
//! symmetric-definite eigenproblem A·x = λ·B·x) run once per model load on
//! 128×128 f64 matrices, so performance is irrelevant — only numerical parity
//! with LAPACK `*sygv` matters (validated by the Python-fixture tests in
//! `plda.rs`).

use std::fmt::{Display, Formatter};

use nalgebra::{Cholesky, DMatrix, Dyn, SymmetricEigen};
use ndarray::{Array1, Array2};

#[derive(Debug)]
pub enum LinalgError {
    /// Matrix inversion failed (singular input).
    Singular(&'static str),
    /// Cholesky factorization failed (matrix not symmetric positive-definite).
    NotSpd(&'static str),
}

impl Display for LinalgError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Singular(what) => write!(f, "singular matrix in {what}"),
            Self::NotSpd(what) => write!(f, "matrix not positive-definite in {what}"),
        }
    }
}

impl std::error::Error for LinalgError {}

fn to_dmatrix(m: &Array2<f64>) -> DMatrix<f64> {
    // ndarray iterates row-major by default; from_row_iterator matches.
    DMatrix::from_row_iterator(m.nrows(), m.ncols(), m.iter().copied())
}

fn from_dmatrix(m: &DMatrix<f64>) -> Array2<f64> {
    Array2::from_shape_fn((m.nrows(), m.ncols()), |(row, col)| m[(row, col)])
}

/// Force exact symmetry, mirroring LAPACK's UPLO semantics where only one
/// triangle is read: rounding drift between the two triangles must not leak
/// into the factorizations.
fn symmetrize(m: &mut DMatrix<f64>) {
    let n = m.nrows();
    for row in 0..n {
        for col in (row + 1)..n {
            let avg = 0.5 * (m[(row, col)] + m[(col, row)]);
            m[(row, col)] = avg;
            m[(col, row)] = avg;
        }
    }
}

/// Matrix inverse (LU-based), f64.
pub fn inv(m: &Array2<f64>) -> Result<Array2<f64>, LinalgError> {
    let dm = to_dmatrix(m);
    let inverse = dm
        .try_inverse()
        .ok_or(LinalgError::Singular("matrix inverse"))?;
    Ok(from_dmatrix(&inverse))
}

/// Generalized symmetric-definite eigenproblem A·x = λ·B·x (B SPD), matching
/// LAPACK `*sygv` itype=1 semantics: eigenvalues returned ASCENDING, the
/// eigenvectors (columns of the returned matrix) normalized so that
/// xᵀ·B·x = 1. Eigenvector sign is arbitrary, as with LAPACK.
///
/// Method: Cholesky reduction. B = L·Lᵀ, C = L⁻¹·A·L⁻ᵀ (symmetric), solve the
/// standard problem on C, back-transform x = L⁻ᵀ·y.
pub fn eigh_gen(
    a: &Array2<f64>,
    b: &Array2<f64>,
) -> Result<(Array1<f64>, Array2<f64>), LinalgError> {
    let mut a_dm = to_dmatrix(a);
    let mut b_dm = to_dmatrix(b);
    symmetrize(&mut a_dm);
    symmetrize(&mut b_dm);

    let chol: Cholesky<f64, Dyn> =
        Cholesky::new(b_dm).ok_or(LinalgError::NotSpd("generalized eigenproblem"))?;
    let l = chol.l();

    // Y = L⁻¹·A, then C = L⁻¹·(L⁻¹·A)ᵀ = L⁻¹·A·L⁻ᵀ (A symmetric).
    let y = l
        .solve_lower_triangular(&a_dm)
        .ok_or(LinalgError::Singular("triangular solve (L⁻¹·A)"))?;
    let mut c = l
        .solve_lower_triangular(&y.transpose())
        .ok_or(LinalgError::Singular("triangular solve (L⁻¹·Aᵀ·L⁻ᵀ)"))?
        .transpose();
    symmetrize(&mut c);

    let eigen = SymmetricEigen::new(c);

    // nalgebra does not sort eigenpairs; LAPACK returns them ascending.
    let n = eigen.eigenvalues.len();
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by(|&lhs, &rhs| eigen.eigenvalues[lhs].total_cmp(&eigen.eigenvalues[rhs]));

    let l_t = l.transpose();
    let mut eigenvalues = Array1::<f64>::zeros(n);
    let mut eigenvectors = Array2::<f64>::zeros((n, n));
    for (dst, &src) in order.iter().enumerate() {
        eigenvalues[dst] = eigen.eigenvalues[src];
        // Back-transform: solve Lᵀ·x = y (upper-triangular). With ‖y‖ = 1 this
        // yields the xᵀ·B·x = 1 normalization LAPACK uses.
        let x = l_t
            .solve_upper_triangular(&eigen.eigenvectors.column(src).clone_owned())
            .ok_or(LinalgError::Singular("triangular back-transform (L⁻ᵀ·y)"))?;
        for row in 0..n {
            eigenvectors[[row, dst]] = x[row];
        }
    }

    Ok((eigenvalues, eigenvectors))
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_abs_diff_eq;
    use ndarray::array;

    #[test]
    fn inv_matches_identity() {
        let m = array![[4.0, 2.0], [1.0, 3.0]];
        let inverse = inv(&m).unwrap();
        let product = m.dot(&inverse);
        assert_abs_diff_eq!(product[[0, 0]], 1.0, epsilon = 1e-12);
        assert_abs_diff_eq!(product[[0, 1]], 0.0, epsilon = 1e-12);
        assert_abs_diff_eq!(product[[1, 0]], 0.0, epsilon = 1e-12);
        assert_abs_diff_eq!(product[[1, 1]], 1.0, epsilon = 1e-12);
    }

    #[test]
    fn inv_rejects_singular() {
        let m = array![[1.0, 2.0], [2.0, 4.0]];
        assert!(inv(&m).is_err());
    }

    #[test]
    fn eigh_gen_solves_the_generalized_problem() {
        // A and B symmetric, B SPD.
        let a = array![[2.0, 1.0, 0.0], [1.0, 3.0, 1.0], [0.0, 1.0, 2.0]];
        let b = array![[4.0, 1.0, 0.0], [1.0, 5.0, 1.0], [0.0, 1.0, 3.0]];

        let (eigenvalues, eigenvectors) = eigh_gen(&a, &b).unwrap();

        // Ascending order.
        assert!(eigenvalues[0] <= eigenvalues[1] && eigenvalues[1] <= eigenvalues[2]);

        for idx in 0..3 {
            let x = eigenvectors.column(idx).to_owned();
            let ax = a.dot(&x);
            let bx = b.dot(&x);
            // A·x = λ·B·x
            for row in 0..3 {
                assert_abs_diff_eq!(ax[row], eigenvalues[idx] * bx[row], epsilon = 1e-10);
            }
            // xᵀ·B·x = 1 (sygv normalization)
            assert_abs_diff_eq!(x.dot(&bx), 1.0, epsilon = 1e-10);
        }
    }

    #[test]
    fn eigh_gen_rejects_non_spd_b() {
        let a = array![[1.0, 0.0], [0.0, 1.0]];
        let b = array![[1.0, 0.0], [0.0, -1.0]];
        assert!(eigh_gen(&a, &b).is_err());
    }
}
