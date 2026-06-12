#include <iostream>
#include <iomanip>
#include <cmath>

#include "correction.h"

int main(int argc, char **argv)
{
  if (argc != 2)
  {
    std::cerr << "Usage: " << argv[0] << " lwtnn_correction.json\n";
    return 1;
  }

  const std::string json_path = argv[1];
  auto correction_set = correction::CorrectionSet::from_file(json_path);
  auto correction = correction_set->at("electron_fastsim_sf");

  // Mock "GEN-matched" electron values (replace with real NanoAOD lookup later)
  const double gen_pt = 15.0;
  const double gen_eta = 0.4;
  const double gen_phi = 2.1;
  const double gen_iso = 1e-3;

  double sf = correction->evaluate({gen_pt, gen_eta, gen_phi, gen_iso});

  std::cout << std::setprecision(17);
  std::cout << "sf_fullOverFast " << sf << "\n";

  return 0;
}
