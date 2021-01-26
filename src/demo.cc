#include <cstdio>
#include "correction.h"

int main(int argc, char** argv) {
  if ( argc == 2 ) {
    auto cset = CorrectionSet(std::string(argv[1]));
    for (auto& corr : cset) {
      printf("Correction: %s\n", corr.name().c_str());
    }
    double out = cset["scalefactors_Tight_Electron"].evaluate({1.3, 25.});
    printf("scalefactors_Tight_Electron(1.3, 25) = %f\n", out);
    out = cset["DeepCSV_2016LegacySF"].evaluate({"central", 0, 1.2, 35., 0.01});
    printf("DeepCSV_2016LegacySF('central', 0, 1.2, 35., 0.5) = %f\n", out);
    double stuff {0.};
    int n { 1000000 };
    for(size_t i=0; i<n; ++i) {
      stuff += cset["DeepCSV_2016LegacySF"].evaluate({"central", 0, 1.2, 35., i / (double) n});
    }
  } else {
    printf("Usage: %s filename.json\n", argv[0]);
  }
}
