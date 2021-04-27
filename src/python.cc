#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "correction.h"

namespace py = pybind11;
using namespace correction;

PYBIND11_MODULE(_core, m) {
    m.doc() = "python binding for corrections evaluator";

    py::class_<Correction, std::shared_ptr<Correction>>(m, "Correction")
        .def_property_readonly("name", &Correction::name)
        .def_property_readonly("description", &Correction::description)
        .def_property_readonly("version", &Correction::version)
        .def("evaluate", [](Correction& c, py::args args) {
          return c.evaluate(py::cast<std::vector<Variable::Type>>(args));
        })
        .def("evalv", [](Correction& c, py::args args) {
          std::vector<Variable::Type> inputs;
          inputs.reserve(py::len(args));
          std::vector<std::pair<size_t, py::buffer_info>> vargs;
          if ( py::len(args) != c.inputs().size() ) {
            throw std::invalid_argument("Incorrect number of inputs (got " + std::to_string(py::len(args))
                + ", expected " + std::to_string(c.inputs().size()) + ")");
          }
          for (size_t i=0; i < py::len(args); ++i) {
            if ( py::isinstance<py::array>(args[i]) ) {
              if ( c.inputs()[i].type() == Variable::VarType::integer ) {
                vargs.emplace_back(i, py::cast<py::array_t<int, py::array::c_style | py::array::forcecast>>(args[i]).request());
                inputs.emplace_back(0);
              }
              else if ( c.inputs()[i].type() == Variable::VarType::real ) {
                vargs.emplace_back(i, py::cast<py::array_t<double, py::array::c_style | py::array::forcecast>>(args[i]).request());
                inputs.emplace_back(0.0);
              }
              else {
                throw std::invalid_argument("Array arguments only allowed for integer and real input types");
              }

              if ( vargs.back().second.ndim != 1 ) {
                throw std::invalid_argument("Array arguments with dimension greater "
                    "than one are not supported (argument at position " + std::to_string(i) + ")");
              }
              if ( vargs.back().second.size != vargs.front().second.size ) {
                throw std::invalid_argument("Array arguments must all have the same size"
                    "(argument at position " + std::to_string(i) + " is length "
                    + std::to_string(vargs.back().second.size) + ")");
              }
            }
            else {
              inputs.push_back(py::cast<Variable::Type>(args[i]));
            }
          }
          auto output = py::array_t<double>((vargs.size() > 0) ? vargs.front().second.size : 1);
          py::buffer_info outbuffer = output.request();
          double * outptr = static_cast<double*>(outbuffer.ptr);
          for (size_t i=0; i < outbuffer.shape[0]; ++i) {
            for (const auto& varg : vargs) {
              if ( std::holds_alternative<int>(inputs[varg.first]) ) {
                inputs[varg.first] = static_cast<int*>(varg.second.ptr)[i];
              }
              else if ( std::holds_alternative<double>(inputs[varg.first]) ) {
                inputs[varg.first] = static_cast<double*>(varg.second.ptr)[i];
              }
            }
            outptr[i] = c.evaluate(inputs);
          }
          return output;
        });

    py::class_<CorrectionSet>(m, "CorrectionSet")
        .def_static("from_file", &CorrectionSet::from_file)
        .def_static("from_string", &CorrectionSet::from_string)
        .def_property_readonly("schema_version", &CorrectionSet::schema_version)
        .def("__getitem__", &CorrectionSet::at, py::return_value_policy::move)
        .def("__len__", &CorrectionSet::size)
        .def("__iter__", [](const CorrectionSet &v) {
          return py::make_key_iterator(v.begin(), v.end());
        }, py::keep_alive<0, 1>());
}
