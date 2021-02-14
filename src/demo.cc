#include <cstdio>
#include "correction.h"

using namespace correction;

int main(int argc, char** argv) {
  if ( argc == 1 ) {
    printf("sizeof(Binning): %lu\n", sizeof(Binning));
    printf("sizeof(MultiBinning): %lu\n", sizeof(MultiBinning));
    printf("sizeof(Category): %lu\n", sizeof(Category));
    printf("sizeof(Formula): %lu\n", sizeof(Formula));
  }
  else if ( argc == 2 ) {
    auto cset = CorrectionSet::from_file(std::string(argv[1]));
    for (auto& corr : *cset) {
      printf("Correction: %s\n", corr.first.c_str());
    }
    double out = cset->at("scalefactors_Tight_Electron")->evaluate({1.3, 25.});
    printf("scalefactors_Tight_Electron(1.3, 25) = %f\n", out);
    auto deepcsv = cset->at("DeepCSV_2016LegacySF");
    printf("deepcsv correction use count: %lu\n", deepcsv.use_count());
    cset.reset(nullptr);
    printf("deepcsv correction use count: %lu\n", deepcsv.use_count());
    out = deepcsv->evaluate({"central", 0, 1.2, 35., 0.01});
    printf("DeepCSV_2016LegacySF('central', 0, 1.2, 35., 0.5) = %f\n", out);
    double stuff {0.};
    int n { 1000000 };
    for(size_t i=0; i<n; ++i) {
      stuff += deepcsv->evaluate({"central", 0, 1.2, 35., i / (double) n});
    }
  }
  else if ( argc == 3 ) {
    rapidjson::Document json;
    std::string doc = R"(
    [
        {
            "expression": ")" + std::string(argv[1]) + R"( ",
            "parser": "TFormula",
            "parameters": [ 0 ]
        },
        {
            "name": "a_variable",
            "type": "real"
        }
    ]
    )";
    json.Parse(doc.c_str());
    auto f = Formula(json.GetArray()[0]);
    auto i = Variable(json.GetArray()[1]);
    std::cout << f.evaluate({i}, {std::stod(argv[2])}) << '\n';
  } else {
    printf("Usage:%s filename.json\n", argv[0]);
  }
}
