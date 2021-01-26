#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "correction.h"

namespace py = pybind11;

PYBIND11_MODULE(libcorrection, m) {
    m.doc() = "python binding for corrections evaluator";

    py::class_<Correction>(m, "Correction")
        .def("name", &Correction::name)
        .def("evaluate", [](Correction& c, py::args args) {
          std::vector<Variable::Type> varargs;
          for (auto handle : args) {
            if ( py::isinstance<py::int_>(handle) ) {
              varargs.push_back(py::cast<int>(handle));
            }
            else if ( py::isinstance<py::float_>(handle) ) {
              varargs.push_back(py::cast<double>(handle));
            }
            else if ( py::isinstance<py::str>(handle) ) {
              varargs.push_back(py::cast<std::string>(handle));
            }
            else {
              throw std::runtime_error("Cannot interpret argument");
            }
          }
          return c.evaluate(varargs);
        }); 

    py::class_<CorrectionSet>(m, "CorrectionSet")
        .def(py::init<const std::string &>())
        .def("__getitem__", &CorrectionSet::operator[])
        .def("__len__", &CorrectionSet::size)
        .def("__iter__", [](const CorrectionSet &v) {
          // FIXME: this is not a mapping
          return py::make_iterator(v.begin(), v.end());
        }, py::keep_alive<0, 1>());
}
