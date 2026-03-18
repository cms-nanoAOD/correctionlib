#include <iostream>
#include <iomanip>
#include <cmath>

#include "correction.h"

static constexpr double PT_EPS  = 1e-4;
static constexpr double ISO_EPS = 1e-6;

static double safe_log10(double x, double eps) {
  return std::log10(std::max(x, eps));
}

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "Usage: " << argv[0] << " lwtnn_correction.json\n";
    return 1;
  }

  const std::string json_path = argv[1];
  auto correction_set = correction::CorrectionSet::from_file(json_path);
  auto correction = correction_set->at("electron_sf");

  // Mock "GEN-matched" electron values (replace with real NanoAOD lookup later)
  const double gen_pt  = 15.0;
  const double gen_eta = 0.4;
  const double gen_phi = 2.1;
  const double gen_iso = 1e-3;

  const double pt_log10  = safe_log10(gen_pt,  PT_EPS);
  const double iso_log10 = safe_log10(gen_iso, ISO_EPS);

  double sf = correction->evaluate({pt_log10, gen_eta, gen_phi, iso_log10});

  std::cout << std::setprecision(17);
  std::cout << "sf_fullOverFast " << sf << "\n";

  return 0;
}
