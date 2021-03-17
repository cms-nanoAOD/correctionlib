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
