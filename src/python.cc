#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "correction.h"

namespace py = pybind11;

PYBIND11_MODULE(libcorrection, m) {
    m.doc() = "python binding for corrections evaluator";

    py::class_<Correction>(m, "Correction")
        .def("name", &Correction::name)
        .def("evaluate", [](Correction& c, py::args args) {
          return c.evaluate(py::cast<std::vector<Variable::Type>>(args));
        }); 

    py::class_<CorrectionSet>(m, "CorrectionSet")
        .def(py::init<const std::string &>())
        .def("__getitem__", &CorrectionSet::operator[], py::return_value_policy::reference_internal)
        .def("__len__", &CorrectionSet::size)
        .def("__iter__", [](const CorrectionSet &v) {
          // FIXME: this is not a mapping
          return py::make_iterator(v.begin(), v.end());
        }, py::keep_alive<0, 1>());
}
