//! Transcendental functions with the same bits on every host (I-733).
//!
//! `f64::sin`, `cos`, `tan`, `asin`, `atan2`, `hypot`, `powf`, `cbrt`, `exp`,
//! `ln` and `tanh` call the host's C library (Apple libm, bionic, glibc),
//! whose answers differ in the last bit: in 2026-11-07's measurement between
//! macOS and the Linux of 5173, up to 39% of `tan`'s and 4% of `sin`'s answers
//! differed, and three works of 29 drew another SVG. Everything the core draws,
//! compiles or digests computes them with the pure-Rust `libm` crate instead.
//! The core's `clippy.toml` refuses the `f64` methods.
//!
//! `sqrt`, `floor`, `ceil`, `round`, `abs` and the arithmetic operators are
//! correctly rounded by IEEE 754 and stay as they are; `powi` is a chain of
//! multiplications that does not reach the C library.

/// The host-independent forms of `f64`'s transcendental methods, named after
/// them with a `d` (deterministic): `x.dsin()` for `x.sin()`.
pub trait DetFloat: Sized {
    fn dsin(self) -> Self;
    fn dcos(self) -> Self;
    fn dtan(self) -> Self;
    fn dsin_cos(self) -> (Self, Self);
    fn dasin(self) -> Self;
    fn datan2(self, other: Self) -> Self;
    fn dhypot(self, other: Self) -> Self;
    fn dpowf(self, exponent: Self) -> Self;
    fn dcbrt(self) -> Self;
    fn dexp(self) -> Self;
    fn dln(self) -> Self;
    fn dtanh(self) -> Self;
}

impl DetFloat for f64 {
    #[inline]
    fn dsin(self) -> f64 {
        libm::sin(self)
    }
    #[inline]
    fn dcos(self) -> f64 {
        libm::cos(self)
    }
    #[inline]
    fn dtan(self) -> f64 {
        libm::tan(self)
    }
    #[inline]
    fn dsin_cos(self) -> (f64, f64) {
        libm::sincos(self)
    }
    #[inline]
    fn dasin(self) -> f64 {
        libm::asin(self)
    }
    #[inline]
    fn datan2(self, other: f64) -> f64 {
        libm::atan2(self, other)
    }
    #[inline]
    fn dhypot(self, other: f64) -> f64 {
        libm::hypot(self, other)
    }
    #[inline]
    fn dpowf(self, exponent: f64) -> f64 {
        libm::pow(self, exponent)
    }
    #[inline]
    fn dcbrt(self) -> f64 {
        libm::cbrt(self)
    }
    #[inline]
    fn dexp(self) -> f64 {
        libm::exp(self)
    }
    #[inline]
    fn dln(self) -> f64 {
        libm::log(self)
    }
    #[inline]
    fn dtanh(self) -> f64 {
        libm::tanh(self)
    }
}

#[cfg(test)]
mod tests {
    use super::DetFloat;

    #[test]
    fn the_functions_answer_with_libm_bits() {
        // Values libm 0.2.16 gives on every host; the std methods gave
        // other last bits on macOS or Linux for inputs like these.
        let x = 0.734_f64;
        assert_eq!(x.dsin().to_bits(), libm::sin(x).to_bits());
        assert_eq!(x.dsin_cos(), (libm::sin(x), libm::cos(x)));
        assert_eq!(3.0_f64.dhypot(4.0), 5.0);
        assert_eq!(8.0_f64.dcbrt(), 2.0);
        assert_eq!(2.0_f64.dpowf(10.0), 1024.0);
        assert_eq!(0.0_f64.dexp(), 1.0);
        assert_eq!(1.0_f64.dln(), 0.0);
        assert_eq!(0.0_f64.datan2(1.0), 0.0);
        assert_eq!(0.0_f64.dtanh(), 0.0);
        assert_eq!(1.0_f64.dasin(), std::f64::consts::FRAC_PI_2);
    }
}
