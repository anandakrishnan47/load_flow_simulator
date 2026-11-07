
from dataclasses import dataclass, field
from typing import Literal


BusType = Literal["Slack", "PV", "PQ"]
LoadType = Literal["PQ", "Z", "ZIP"]


@dataclass
class Bus:
    number: int
    name: str
    base_kv: float
    bus_type: BusType = "PQ"
    vm: float = 1.0
    va: float = 0.0
    vmin: float = 0.95
    vmax: float = 1.05
    area: int = 1
    in_service: bool = True


@dataclass
class Line:
    from_bus: int
    to_bus: int
    r: float
    x: float
    b: float = 0.0
    rating_mva: float = 100.0
    in_service: bool = True


@dataclass
class Transformer:
    from_bus: int
    to_bus: int
    r: float
    x: float
    rating_mva: float
    tap_ratio: float = 1.0
    phase_shift: float = 0.0
    tap_side: str = "from"
    in_service: bool = True


@dataclass
class Generator:
    bus: int
    pg: float
    vg: float = 1.0
    qmin: float = -999.0
    qmax: float = 999.0
    qg: float = 0.0
    in_service: bool = True


@dataclass
class Load:
    bus: int
    pd: float
    qd: float
    model: LoadType = "PQ"
    zip_p: tuple = (1.0, 0.0, 0.0)
    zip_q: tuple = (1.0, 0.0, 0.0)
    in_service: bool = True


@dataclass
class Shunt:
    bus: int
    gs: float = 0.0
    bs: float = 0.0
    in_service: bool = True


@dataclass
class ExternalGrid:
    bus: int
    vm: float = 1.0
    va: float = 0.0
    in_service: bool = True


@dataclass
class Network:
    base_mva: float = 100.0
    frequency: float = 50.0

    buses: list[Bus] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    transformers: list[Transformer] = field(default_factory=list)
    generators: list[Generator] = field(default_factory=list)
    loads: list[Load] = field(default_factory=list)
    shunts: list[Shunt] = field(default_factory=list)
    external_grids: list[ExternalGrid] = field(
        default_factory=list
    )

    def add_bus(self, bus: Bus):
        if bus.base_kv <= 0:
            raise ValueError("Base kV must be positive")

        if any(b.number == bus.number for b in self.buses):
            raise ValueError("Duplicate bus number")

        self.buses.append(bus)

    def bus_exists(self, number: int) -> bool:
        return any(b.number == number for b in self.buses)

    def add_line(self, line: Line):
        if not self.bus_exists(line.from_bus):
            raise ValueError("From bus does not exist")

        if not self.bus_exists(line.to_bus):
            raise ValueError("To bus does not exist")

        if line.from_bus == line.to_bus:
            raise ValueError("Line cannot connect to itself")

        if line.r == 0 and line.x == 0:
            raise ValueError("Line impedance cannot be zero")

        if line.rating_mva <= 0:
            raise ValueError("Invalid line rating")

        self.lines.append(line)

    def add_transformer(self, transformer: Transformer):
        if not self.bus_exists(transformer.from_bus):
            raise ValueError("Transformer from bus missing")

        if not self.bus_exists(transformer.to_bus):
            raise ValueError("Transformer to bus missing")

        if transformer.from_bus == transformer.to_bus:
            raise ValueError("Transformer buses must differ")

        if transformer.tap_ratio <= 0:
            raise ValueError("Invalid tap ratio")

        if transformer.rating_mva <= 0:
            raise ValueError("Invalid transformer rating")

        if transformer.r == 0 and transformer.x == 0:
            raise ValueError("Transformer impedance cannot be zero")

        self.transformers.append(transformer)

    def add_generator(self, generator: Generator):
        if not self.bus_exists(generator.bus):
            raise ValueError("Generator bus missing")

        if generator.qmin > generator.qmax:
            raise ValueError("Invalid generator Q limits")

        self.generators.append(generator)

    def add_load(self, load: Load):
        if not self.bus_exists(load.bus):
            raise ValueError("Load bus missing")

        self.loads.append(load)

    def add_shunt(self, shunt: Shunt):
        if not self.bus_exists(shunt.bus):
            raise ValueError("Shunt bus missing")

        self.shunts.append(shunt)

    def add_external_grid(self, grid: ExternalGrid):
        if not self.bus_exists(grid.bus):
            raise ValueError("External grid bus missing")

        self.external_grids.append(grid)
