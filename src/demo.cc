#include "rapidjson/document.h"
#include "rapidjson/filereadstream.h"
#include <cstdio>
#include <string>


rapidjson::Document readjson(std::string fn) {
  rapidjson::Document d;

  FILE* fp = fopen(fn.c_str(), "rb");
  char readBuffer[65536];
  rapidjson::FileReadStream is(fp, readBuffer, sizeof(readBuffer));
  d.ParseStream(is);
  fclose(fp);

  // TODO: validate with https://rapidjson.org/md_doc_schema.html
  auto schema_version = d["schema_version"].GetInt();
  return d;
}


int main() {
  auto doc = readjson("corrections.json");
  for (auto& corr : doc["corrections"].GetArray()) {
    printf("Correction: %s\n", corr["name"].GetString());
  }
}
